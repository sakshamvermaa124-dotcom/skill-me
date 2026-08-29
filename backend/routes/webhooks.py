"""
SkillMe — Inbound Webhooks
Public endpoints that external services call into. Not protected by X-Admin-Key —
authenticated instead via a shared secret in the URL (see BREVO_WEBHOOK_SECRET).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from db.database import db
from config import settings

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
