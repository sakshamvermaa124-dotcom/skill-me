"""
SkillMe — Inbound Webhooks
Public endpoints that external services call into. Not protected by X-Admin-Key —
authenticated instead via a shared secret in the URL (see BREVO_WEBHOOK_SECRET).
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from db.database import db
from config import settings
from services import payment_service
from services.certificate_service import certificate_service
from services.email_service import email_service

logger = logging.getLogger("skillme.webhooks")
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Brevo event name -> email_logs column(s) it updates
_TIMESTAMP_EVENTS = {
    "delivered": "delivered_at",
    "hard_bounce": "bounced_at",
    "soft_bounce": "bounced_at",
    "blocked": "bounced_at",
    "invalid_email": "bounced_at",
    "spam": "spam_reported_at",
    "unsubscribed": "unsubscribed_at",
}
_BOUNCE_TYPES = {
    "hard_bounce": "hard",
    "soft_bounce": "soft",
    "blocked": "blocked",
    "invalid_email": "invalid",
}


def _extract_log_id(payload: dict) -> int | None:
    """
    Tags are minted as f"log{id}" in email_service._send_and_log — parse the id back out.
    Brevo's field name/shape for the tag varies by payload version, so check every
    place it's been observed to show up: "tag" (string), "tags" (list), "X-Mailin-Tag".
    """
    candidates = []
    tag = payload.get("tag")
    if isinstance(tag, str):
        candidates.append(tag)
    tags = payload.get("tags")
    if isinstance(tags, list):
        candidates.extend(t for t in tags if isinstance(t, str))
    header_tag = payload.get("X-Mailin-Tag")
    if isinstance(header_tag, str):
        candidates.append(header_tag)

    for candidate in candidates:
        if candidate.startswith("log"):
            try:
                return int(candidate[3:])
            except ValueError:
                continue
    return None


async def _apply_event(payload: dict) -> None:
    event = (payload.get("event") or "").lower()
    log_id = _extract_log_id(payload)
    if log_id is None:
        # No tag matched (e.g. email sent before this feature shipped, or Brevo's
        # payload shape doesn't match what we're parsing) — log so it's visible,
        # but don't fail the request.
        logger.info("Brevo webhook event %r had no matching log id — raw payload: %s", event, payload)
        return
    logger.info("Brevo webhook event %r matched log id %s", event, log_id)

    now = datetime.now(timezone.utc).isoformat()
    sets = ["last_event = ?", "last_event_at = ?"]
    params: list = [event, now]

    if event == "opened":
        sets.append("opened_at = COALESCE(opened_at, ?)")
        sets.append("opened_count = COALESCE(opened_count, 0) + 1")
        params.append(now)
    elif event in ("click", "clicked"):
        sets.append("clicked_at = COALESCE(clicked_at, ?)")
        sets.append("clicked_count = COALESCE(clicked_count, 0) + 1")
        params.append(now)
    elif event in _TIMESTAMP_EVENTS:
        column = _TIMESTAMP_EVENTS[event]
        sets.append(f"{column} = COALESCE({column}, ?)")
        params.append(now)
        if event in _BOUNCE_TYPES:
            sets.append("bounce_type = ?")
            params.append(_BOUNCE_TYPES[event])

    params.append(log_id)
    try:
        await db.execute(
            f"UPDATE email_logs SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        )
    except Exception as exc:
        logger.warning("Failed to apply Brevo webhook event %s for log %s: %s", event, log_id, exc)


@router.post("/brevo", summary="Receive Brevo email event webhooks (delivered/opened/clicked/bounced/...)")
async def brevo_webhook(request: Request, key: str | None = None):
    """
    Configure this URL in Brevo → Transactional → Settings → Webhooks:
      https://<backend>/api/webhooks/brevo?key=<BREVO_WEBHOOK_SECRET>

    Brevo POSTs one event object per request (or a batch array, depending on
    account settings) — handle both shapes. Always returns 200 so Brevo doesn't
    retry/disable the webhook on our account; failures are logged, not raised.
    """
    if settings.brevo_webhook_secret and key != settings.brevo_webhook_secret:
        logger.warning("Rejected Brevo webhook call with invalid/missing key")
        return {"status": "ignored"}

    try:
        body = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "invalid JSON"}

    logger.info("Brevo webhook raw body: %s", body)
    events = body if isinstance(body, list) else [body]
    for payload in events:
        if isinstance(payload, dict):
            await _apply_event(payload)

    return {"status": "ok", "processed": len(events)}


@router.post("/razorpay", summary="Receive Razorpay payment webhooks (authorized/captured/failed)")
async def razorpay_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Configure in Razorpay Dashboard > Webhooks with events payment.authorized, payment.captured,
    payment.failed and order.paid, using RAZORPAY_WEBHOOK_SECRET. This confirms payments even when
    the student closes the tab before the browser calls /payments/verify.

    Authenticated by the X-Razorpay-Signature HMAC over the raw body. Idempotent: each event id
    (X-Razorpay-Event-Id) is stored once, and a replay, or an event for an already-paid order, is a no-op.
    """
    raw = await request.body()
    secret = settings.razorpay_webhook_secret
    sig = request.headers.get("X-Razorpay-Signature", "")
    if not secret or not hmac.compare_digest(hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(), sig):
        logger.warning("Rejected Razorpay webhook: bad or unconfigured signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        body = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = body.get("event") or ""
    payload = body.get("payload") or {}
    entity = (payload.get("payment") or {}).get("entity") or {}
    order_id = entity.get("order_id") or ((payload.get("order") or {}).get("entity") or {}).get("id")
    payment_id = entity.get("id")
    event_id = request.headers.get("X-Razorpay-Event-Id") or f"{event}:{order_id}:{payment_id}"

    seen = await db.fetch_one("SELECT id FROM payment_events WHERE provider_event_id = ?", (event_id,))
    if seen:
        return {"status": "duplicate"}
    await db.execute(
        """INSERT INTO payment_events (provider_event_id, event_type, razorpay_order_id, razorpay_payment_id, payload)
           VALUES (?, ?, ?, ?, ?) ON CONFLICT(provider_event_id) DO NOTHING""",
        (event_id, event, order_id, payment_id, raw.decode("utf-8", "replace")[:20000]),
    )

    if not order_id:
        return {"status": "ignored"}

    if event in ("payment.captured", "order.paid"):
        order, newly_paid = await payment_service.mark_paid(order_id, payment_id, via="webhook")
        if order and newly_paid:
            try:
                cert = await certificate_service.issue_certificate(
                    order["student_id"], order["batch_id"], suppress_email=True, via="payment", payment_id=order["id"]
                )
                student = await db.fetch_one(
                    "SELECT first_name, last_name, email, domain FROM students WHERE id = ?", (order["student_id"],)
                )
                if student:
                    background_tasks.add_task(
                        email_service.send_certificate_ready,
                        first_name=student["first_name"], last_name=student["last_name"],
                        email=student["email"], domain=student["domain"] or "web-dev", cert_id=cert["cert_id"],
                    )
            except ValueError as exc:
                logger.warning("Webhook paid order %s but certificate not issued: %s", order_id, exc)
    elif event == "payment.authorized":
        await payment_service.mark_pending(order_id, payment_id)
    elif event == "payment.failed":
        await payment_service.mark_failed(order_id, entity.get("error_code"), entity.get("error_description"))
    return {"status": "ok"}
