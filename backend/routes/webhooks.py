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


def _extract_log_id(tag: str | None) -> int | None:
    """Tags are minted as f"log{id}" in email_service._send_and_log — parse the id back out."""
    if not tag or not tag.startswith("log"):
        return None
    try:
        return int(tag[3:])
    except ValueError:
        return None


async def _apply_event(payload: dict) -> None:
    event = (payload.get("event") or "").lower()
    tag = payload.get("tag")
    log_id = _extract_log_id(tag)
    if log_id is None:
        # No tag (e.g. email sent before this feature shipped) — nothing to match it to.
        return

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

    events = body if isinstance(body, list) else [body]
    for payload in events:
        if isinstance(payload, dict):
            await _apply_event(payload)

    return {"status": "ok", "processed": len(events)}
