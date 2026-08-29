"""
One-time backfill of open/click/bounce/spam data for emails sent BEFORE the
Brevo webhook (see routes/webhooks.py) was configured.

Webhooks are forward-only — Brevo never replays past events to a newly added
webhook URL. This script instead pulls historical events straight from Brevo's
statistics API and matches them back onto existing email_logs rows.

Requires BREVO_API_KEY in .env (Settings -> SMTP & API -> API Keys in the Brevo
dashboard — this is a different key from the SMTP_PASSWORD used for sending).

Brevo's events endpoint only retains a limited window of history (varies by
plan, commonly 30-90 days), so this can only backfill emails sent recently —
it cannot resurrect data for emails sent long ago.

Matching strategy: Brevo groups events by messageId, which we don't store on
older rows, so instead every messageId's events are matched to the closest
untagged email_logs row with the same recipient + subject sent within a
5-minute window. Safe to re-run — already-populated columns are left alone
(COALESCE), so results only get filled in, never overwritten.

Usage:
    python backend/scripts/backfill_email_engagement.py [--days 30]
"""

import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from db.database import db

BREVO_EVENTS_URL = "https://api.brevo.com/v3/smtp/statistics/events"
PAGE_SIZE = 500
MATCH_WINDOW = timedelta(minutes=5)

# Brevo event name -> (email_logs timestamp column, optional bounce_type value)
_TIMESTAMP_EVENTS = {
    "delivered": ("delivered_at", None),
    "hard_bounce": ("bounced_at", "hard"),
    "soft_bounce": ("bounced_at", "soft"),
    "blocked": ("bounced_at", "blocked"),
    "invalid_email": ("bounced_at", "invalid"),
    "spam": ("spam_reported_at", None),
    "unsubscribed": ("unsubscribed_at", None),
}


def _parse_date(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


async def fetch_all_events(days: int) -> list[dict]:
    if not settings.brevo_api_key:
        print("BREVO_API_KEY is not set in .env — cannot call Brevo's statistics API.")
        sys.exit(1)

    events: list[dict] = []
    offset = 0
    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            resp = await client.get(
                BREVO_EVENTS_URL,
                headers={"api-key": settings.brevo_api_key, "accept": "application/json"},
                params={"limit": PAGE_SIZE, "offset": offset, "days": days},
            )
            resp.raise_for_status()
            data = resp.json()
            page = data.get("events", []) if isinstance(data, dict) else data
            if not page:
                break
            events.extend(page)
            print(f"  fetched {len(events)} events so far...")
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
    return events


async def main(days: int):
    print("=" * 65)
    print("  Email Engagement Backfill — pulling history from Brevo")
    print("=" * 65)

    await db.connect()

    print(f"\nFetching events from the last {days} day(s)...")
    events = await fetch_all_events(days)
    print(f"Fetched {len(events)} total events.")
    if not events:
        print("Nothing to backfill.")
        return

    # Group events by Brevo messageId — one group == one sent email
    by_message: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        mid = e.get("messageId") or e.get("message-id") or ""
        if mid:
            by_message[mid].append(e)

    print(f"Grouped into {len(by_message)} unique messages.")

    # Candidate rows: anything without a message_tag is from before tagging existed
    rows = await db.fetch_all(
        "SELECT id, recipient_email, subject, sent_at FROM email_logs WHERE message_tag IS NULL"
    )
    print(f"{len(rows)} untagged (pre-webhook) rows in email_logs to match against.")

    # Pre-index candidate rows by (email, subject) for fast lookup
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = ((r["recipient_email"] or "").lower(), r["subject"] or "")
        by_key[key].append(r)

    claimed_ids: set[int] = set()
    matched = 0
    unmatched = 0

    for mid, group in by_message.items():
        email = (group[0].get("email") or "").lower()
        subject = group[0].get("subject") or ""
        candidates = by_key.get((email, subject), [])
        if not candidates:
            unmatched += 1
            continue

        # Pick the closest un-claimed row in time to the first event in this group
        first_event_time = min(_parse_date(e["date"]) for e in group if e.get("date"))
        best, best_diff = None, None
        for r in candidates:
            if r["id"] in claimed_ids:
                continue
            try:
                sent_at = _parse_date(r["sent_at"].replace(" ", "T") if " " in r["sent_at"] else r["sent_at"])
            except Exception:
                continue
            diff = abs((sent_at.replace(tzinfo=timezone.utc) if sent_at.tzinfo is None else sent_at) - first_event_time)
            if diff <= MATCH_WINDOW and (best_diff is None or diff < best_diff):
                best, best_diff = r, diff

        if not best:
            unmatched += 1
            continue

        claimed_ids.add(best["id"])
        await apply_events(best["id"], group)
        matched += 1

    print()
    print("=" * 65)
    print(f"  DONE — {matched} messages matched and applied, {unmatched} unmatched")
    print("  (unmatched events are usually from emails sent by other Brevo")
    print("   senders on the same account, or outside the untagged row set)")
    print("=" * 65)


async def apply_events(log_id: int, group: list[dict]) -> None:
    sets: list[str] = []
    params: list = []

    opens = [e for e in group if e.get("event") == "opened"]
    clicks = [e for e in group if e.get("event") in ("click", "clicked")]

    if opens:
        sets.append("opened_at = COALESCE(opened_at, ?)")
        params.append(min(e["date"] for e in opens))
        sets.append("opened_count = ?")
        params.append(len(opens))
    if clicks:
        sets.append("clicked_at = COALESCE(clicked_at, ?)")
        params.append(min(e["date"] for e in clicks))
        sets.append("clicked_count = ?")
        params.append(len(clicks))

    for event, (column, bounce_type) in _TIMESTAMP_EVENTS.items():
        matches = [e for e in group if e.get("event") == event]
        if not matches:
            continue
        sets.append(f"{column} = COALESCE({column}, ?)")
        params.append(min(e["date"] for e in matches))
        if bounce_type:
            sets.append("bounce_type = COALESCE(bounce_type, ?)")
            params.append(bounce_type)

    if not sets:
        return

    sets.append("last_event = ?")
    params.append(group[-1].get("event"))
    sets.append("last_event_at = ?")
    params.append(group[-1].get("date"))

    params.append(log_id)
    await db.execute(f"UPDATE email_logs SET {', '.join(sets)} WHERE id = ?", tuple(params))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30, help="How many days of Brevo event history to pull")
    args = parser.parse_args()
    asyncio.run(main(args.days))
