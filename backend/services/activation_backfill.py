"""
SkillMe — Derive historical activation events (read-only on core tables).

Writes ONLY into student_events (source='backfill'), idempotent through dedupe keys.
Rules match analytics_service so historical and live events agree.
"""
from __future__ import annotations

from datetime import datetime

from db.database import db
from services import analytics_service as an
from services.activation_events import record_event


def _fmt(t: datetime | None) -> str | None:
    return t.strftime("%Y-%m-%d %H:%M:%S") if t else None


async def run(now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    raw = await an.load_raw(db)
    students = an.build_students(raw, now)
    enr = await db.fetch_all(
        """SELECT e.student_id, e.batch_id, datetime(e.joined_at) AS joined_at, e.status
           FROM enrollments e""")
    enr_by: dict[int, list[dict]] = {}
    for e in enr:
        enr_by.setdefault(e["student_id"], []).append(e)

    subs_by: dict[tuple, list[dict]] = {}
    for x in raw["submissions"]:
        subs_by.setdefault((x["student_id"], x["batch_id"]), []).append(x)

    created = 0
    for s in students:
        for e in enr_by.get(s["id"], []):
            sid, bid, em = s["id"], e["batch_id"], s["email"]
            joined = an.parse_ts(e["joined_at"])
            created += await record_event("enrollment_created", sid, bid, email=em, at=_fmt(joined), source="backfill")
            if s["first_login_ts"] and e["status"] != "dropped":
                created += await record_event("first_verified_login", sid, bid, email=em,
                                              at=_fmt(s["first_login_ts"]), source="backfill")
            subs = subs_by.get((sid, bid), [])
            if subs:
                first = min(subs, key=lambda x: x["submitted_at"] or "")
                created += await record_event("first_task_submitted", sid, bid, email=em,
                                              at=first["submitted_at"], source="backfill", meta={"week": first["week"]})
            approved = sorted((x for x in subs if x["status"] == "approved"), key=lambda x: x["reviewed_at"] or "")
            for i, x in enumerate(approved):
                created += await record_event("week_approved", sid, bid, email=em, at=x["reviewed_at"],
                                              source="backfill", discriminator=x["week"], meta={"week": x["week"]})
                if i == 0:
                    created += await record_event("first_task_approved", sid, bid, email=em, at=x["reviewed_at"],
                                                  source="backfill", meta={"week": x["week"]})
            if len({x["week"] for x in approved}) >= 4:
                created += await record_event("internship_completed", sid, bid, email=em,
                                              at=approved[-1]["reviewed_at"], source="backfill")
    total = await db.fetch_one("SELECT COUNT(*) AS n FROM student_events")
    return {"created": created, "total_events": total["n"]}
