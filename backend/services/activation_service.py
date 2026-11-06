"""
SkillMe — Student activation segmentation.

Read-only on every core table. Built on analytics_service rows so "logged in", "first task",
"completed" and "last activity" mean exactly what the Analytics page says they mean.

Each enrolled, non-dropped student gets exactly ONE lifecycle stage; overlays
(inactive, eligibility, holdout) are computed separately.
"""
from __future__ import annotations

import json
import zlib
from datetime import datetime, timedelta

from db.database import db
from services import analytics_service as an

INTERNSHIP_DAYS = 28

DEFAULT_CONFIG = {
    "mode": "off",                 # off | dry_run | live
    "student_ui": False,           # show the in-dashboard checklist
    "grace_days": 14,              # after the 28-day window
    "inactive_days": 7,
    "frequency_cap_hours": 48,
    "holdout_pct": 10,
    "baseline": {"first_login_pct": 53.7, "first_task_pct": 38.0, "completion_pct": 43.3,
                 "median_login_to_task_days": 3.2, "weekly_active": 4},
    "targets": {"first_task_pct": 55.0, "completion_pct": 55.0, "median_login_to_task_days": 2.0},
    "triggers": {
        "onboarding_no_login": {"enabled": True, "delays_h": [1, 24, 72]},
        "login_no_first_task": {"enabled": True, "delays_h": [24, 72]},
        "milestone_stall": {"enabled": True, "delays_h": [72, 168]},
        "inactivity": {"enabled": False, "delays_h": [0], "cooldown_days": 7},
        "internship_completed": {"enabled": True, "delays_h": [0]},
    },
}

STAGE_LABELS = {
    "never_logged_in": "Never logged in",
    "no_first_task": "Logged in, no first task",
    "first_task_submitted": "First task submitted",
    "stuck_week_1": "Stuck at Week 1",
    "stuck_week_2": "Stuck at Week 2",
    "stuck_week_3": "Stuck at Week 3",
    "completed": "Completed",
}
STAGE_ORDER = list(STAGE_LABELS)


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


async def get_config() -> dict:
    row = await db.fetch_one("SELECT value FROM engagement_settings WHERE key = 'config'")
    try:
        stored = json.loads(row["value"]) if row and row["value"] else {}
    except (ValueError, TypeError):
        stored = {}
    return _merge(DEFAULT_CONFIG, stored)


async def save_config(patch: dict) -> dict:
    cfg = _merge(await get_config(), patch)
    await db.execute(
        """INSERT INTO engagement_settings (key, value, updated_at) VALUES ('config', ?, CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP""",
        (json.dumps(cfg),),
    )
    return cfg


def is_holdout(student_id: int, pct: int | float) -> bool:
    """Deterministic: a student is always in or always out of the control group."""
    return (zlib.crc32(f"holdout:{student_id}".encode()) % 100) < pct


def lifecycle_stage(s: dict) -> str | None:
    """Exactly one stage for an enrolled, non-dropped student; None otherwise."""
    if not s["is_enrolled"] or s["is_dropped"]:
        return None
    if s["is_completed"]:
        return "completed"
    if not s["is_started"] and not s["has_first_task"]:
        return "never_logged_in"
    if not s["has_first_task"]:
        return "no_first_task"
    approved = s["weeks_approved_set"]
    if not approved:
        return "first_task_submitted"
    return f"stuck_week_{min(max(approved), 3)}"


def window_end(start: datetime | None, grace_days: int) -> datetime | None:
    return start + timedelta(days=INTERNSHIP_DAYS + grace_days) if start else None


def eligibility(s: dict, start: datetime | None, now: datetime, grace_days: int) -> str:
    if s["is_dropped"]:
        return "dropped"
    end = window_end(start, grace_days)
    return "ended" if end and now > end else "active"


async def _batch_info() -> dict[int, dict]:
    """student_id -> {batch_id, start (batch.start_date or enrollment join)} for the live enrollment."""
    rows = await db.fetch_all(
        """SELECT e.student_id, e.batch_id, datetime(COALESCE(b.start_date, e.joined_at)) AS start_at
           FROM enrollments e LEFT JOIN batches b ON b.id = e.batch_id
           WHERE e.status != 'dropped' ORDER BY e.id"""
    )
    out: dict[int, dict] = {}
    for r in rows:
        out[r["student_id"]] = {"batch_id": r["batch_id"], "start": an.parse_ts(r["start_at"])}
    return out


def enrich(s: dict, binfo: dict | None, cfg: dict, now: datetime, last_approved_ts: datetime | None = None) -> dict:
    """Returns the per-student recovery row (a new dict; analytics rows are not mutated)."""
    info = binfo or {}
    stage = lifecycle_stage(s)
    last = s["last_activity_ts"]
    days_idle = (now - last).days if last else None
    approved = s["weeks_approved_set"]
    last_approved = max(approved) if approved else 0
    start = info.get("start") or s["enrolled_ts"]
    elig = eligibility(s, start, now, cfg["grace_days"])
    return {
        "id": s["id"], "batch_id": info.get("batch_id"), "name": s["name"], "email": s["email"],
        "domain_key": s["domain_key"], "domain_label": s["domain_label"],
        "enrolled_ts": s["enrolled_ts"], "start_ts": start,
        "stage": stage, "stage_label": STAGE_LABELS.get(stage, "—"),
        "weeks_approved_set": approved, "last_approved_week": last_approved,
        "current_milestone": None if s["is_completed"] else min((last_approved or 0) + 1, 4),
        "first_login_ts": s["first_login_ts"], "first_submit_ts": s["first_submit_ts"],
        "last_activity_ts": last, "days_idle": days_idle,
        "inactive": bool(stage and stage != "completed" and last and last < now - timedelta(days=cfg["inactive_days"])),
        "eligibility": elig, "holdout": is_holdout(s["id"], cfg["holdout_pct"]),
        "is_test": bool(s["is_test"]), "is_completed": s["is_completed"],
        "last_approved_ts": last_approved_ts, "weeks_reached": s["weeks_reached"],
    }


async def load_recovery_rows(now: datetime | None = None, include_test: bool = False) -> tuple[list[dict], dict]:
    now = now or datetime.utcnow()
    cfg = await get_config()
    raw = await an.load_raw(db)
    students = an.build_students(raw, now)
    binfo = await _batch_info()
    approved_at: dict[int, datetime] = {}
    for x in raw["submissions"]:
        if x["status"] == "approved":
            t = an.parse_ts(x["reviewed_at"])
            if t and (x["student_id"] not in approved_at or t > approved_at[x["student_id"]]):
                approved_at[x["student_id"]] = t
    rows = [enrich(s, binfo.get(s["id"]), cfg, now, approved_at.get(s["id"]))
            for s in students if include_test or not s["is_test"]]
    return [r for r in rows if r["stage"]], cfg


def filter_rows(rows: list[dict], *, stage=None, domain=None, enrolled_from=None, enrolled_to=None,
                activity=None, milestone=None, eligibility_=None, inactive=None, q=None) -> list[dict]:
    start, end = an.ist_date_to_utc(enrolled_from), an.ist_date_to_utc(enrolled_to, end=True)
    buckets = {"0-3": (0, 3), "3-7": (3, 7), "7-14": (7, 14), "14+": (14, 10**6)}
    out = []
    for r in rows:
        if stage and r["stage"] != stage:
            continue
        if domain and r["domain_key"] != domain:
            continue
        if start and (not r["enrolled_ts"] or r["enrolled_ts"] < start):
            continue
        if end and (not r["enrolled_ts"] or r["enrolled_ts"] >= end):
            continue
        if milestone and r["current_milestone"] != int(milestone):
            continue
        if eligibility_ and r["eligibility"] != eligibility_:
            continue
        if inactive and not r["inactive"]:
            continue
        if activity:
            if activity == "never":
                if r["first_login_ts"] or r["first_submit_ts"]:
                    continue
            elif activity in buckets:
                lo, hi = buckets[activity]
                if r["days_idle"] is None or not (lo <= r["days_idle"] < hi):
                    continue
        if q:
            ql = q.lower()
            if ql not in (r["name"] or "").lower() and ql not in (r["email"] or "").lower():
                continue
        out.append(r)
    return out


def summarize(rows: list[dict]) -> dict:
    counts = {k: 0 for k in STAGE_ORDER}
    for r in rows:
        counts[r["stage"]] += 1
    return {
        "total": len(rows),
        "stages": [{"key": k, "label": STAGE_LABELS[k], "count": counts[k]} for k in STAGE_ORDER],
        "inactive_7d": sum(1 for r in rows if r["inactive"]),
        "ended_window": sum(1 for r in rows if r["eligibility"] == "ended"),
    }


async def student_state(student_id: int, batch_id: int | None) -> dict | None:
    """Lightweight single-student state for the dashboard (a few targeted queries, not the full dataset).
    Uses the same rules as build_students: first login = first verified code on/after enrollment - 5 min."""
    st = await db.fetch_one("SELECT id, email, domain FROM students WHERE id = ?", (student_id,))
    if not st:
        return None
    enr = await db.fetch_one(
        """SELECT e.batch_id, e.status, datetime(e.joined_at) AS joined_at, datetime(COALESCE(b.start_date, e.joined_at)) AS start_at,
                  COALESCE(b.domain, ?) AS domain
           FROM enrollments e LEFT JOIN batches b ON b.id = e.batch_id
           WHERE e.student_id = ? AND (? IS NULL OR e.batch_id = ?) AND e.status != 'dropped'
           ORDER BY e.id DESC LIMIT 1""", (st["domain"], student_id, batch_id, batch_id))
    if not enr:
        return None
    subs = await db.fetch_all(
        "SELECT week, status FROM submissions WHERE student_id = ? AND batch_id = ?", (student_id, enr["batch_id"]))
    joined = an.parse_ts(enr["joined_at"])
    logins = await db.fetch_all(
        "SELECT datetime(COALESCE(verified_at, created_at)) AS at FROM otp_tokens WHERE lower(email) = lower(?) AND used = 1",
        (st["email"],))
    after = [t for t in (an.parse_ts(x["at"]) for x in logins) if t and (not joined or t >= joined - timedelta(minutes=5))]
    approved = sorted({x["week"] for x in subs if x["status"] == "approved"})
    row = {"is_enrolled": True, "is_dropped": False, "is_completed": len(approved) >= 4,
           "is_started": bool(after), "has_first_task": bool(subs), "weeks_approved_set": approved}
    return {"student": st, "batch_id": enr["batch_id"], "domain": enr["domain"] or st["domain"],
            "stage": lifecycle_stage(row), "approved": approved, "submitted_weeks": sorted({x["week"] for x in subs}),
            "has_first_task": bool(subs), "start": an.parse_ts(enr["start_at"])}
