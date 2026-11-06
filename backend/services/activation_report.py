"""
SkillMe — Activation reporting by enrollment cohort, versus baseline and targets.

Metric definitions are the ones on the Analytics page (analytics_service.build_students):
  first-login %        = logged in / enrolled
  first-task %         = first task submitted / logged in         (baseline 38%)
  completion %         = completed 4 weeks / first task submitted  (baseline 43.3%)
  login -> first task  = median days between first login and first submission
Read-only.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from db.database import db
from services import activation_service as seg
from services import analytics_service as an

OUTCOME_WINDOW_H = 72
MIN_SAMPLE = 30


def _cohort_key(ts: datetime | None, group: str) -> str:
    if not ts:
        return "unknown"
    ist = ts + an.IST_OFFSET
    if group == "week":
        monday = (ist - timedelta(days=ist.weekday())).date()
        return f"{monday.isoformat()}"
    return f"{ist:%Y-%m}"


def _metrics(group: list[dict], viewed_ids: set[int]) -> dict:
    enrolled = len(group)
    logged = [s for s in group if s["is_started"]]
    first_task = [s for s in group if s["has_first_task"]]
    logged_and_task = [s for s in logged if s["has_first_task"]]
    completed = [s for s in group if s["is_completed"]]
    gaps = [an.days_between(s["first_login_ts"], s["first_submit_ts"]) for s in logged_and_task]
    return {
        "enrolled": enrolled,
        "logged_in": len(logged),
        "first_login_pct": an.pct(len(logged), enrolled),
        "first_task": len(first_task),
        "first_task_pct": an.pct(len(logged_and_task), len(logged)),
        "completed": len(completed),
        "completion_pct": an.pct(len(completed), len(first_task)),
        "median_login_to_task_days": an.median(gaps),
        "first_task_viewed_pct": an.pct(sum(1 for s in group if s["id"] in viewed_ids), enrolled),
    }


def _status(value, target, lower_is_better=False):
    if value is None or target is None:
        return "none"
    ok = value <= target if lower_is_better else value >= target
    return "good" if ok else "off"


def _outcome(trigger: str, s: dict, t0: datetime, sub_times: list[datetime]) -> bool:
    end = t0 + timedelta(hours=OUTCOME_WINDOW_H)
    if trigger == "onboarding_no_login":
        return bool(s["first_login_ts"] and t0 <= s["first_login_ts"] <= end)
    if trigger == "login_no_first_task":
        return bool(s["first_submit_ts"] and t0 <= s["first_submit_ts"] <= end)
    if trigger == "milestone_stall":
        return any(t0 <= t <= end for t in sub_times)
    if trigger == "inactivity":
        return bool(s["last_activity_ts"] and s["last_activity_ts"] > t0 and s["last_activity_ts"] <= end)
    return False


async def build_report(group: str = "month", now: datetime | None = None, include_test: bool = False) -> dict:
    now = now or datetime.utcnow()
    cfg = await seg.get_config()
    raw = await an.load_raw(db)
    students = [s for s in an.build_students(raw, now) if s["is_enrolled"] and (include_test or not s["is_test"])]
    by_id = {s["id"]: s for s in students}

    viewed = {r["student_id"] for r in await db.fetch_all(
        "SELECT DISTINCT student_id FROM student_events WHERE event_type = 'first_task_viewed'")}

    groups: dict[str, list[dict]] = defaultdict(list)
    for s in students:
        groups[_cohort_key(s["enrolled_ts"], group)].append(s)
    targets, base = cfg["targets"], cfg["baseline"]
    cohorts = []
    for key in sorted(groups, reverse=True):
        m = _metrics(groups[key], viewed)
        m["cohort"] = key
        m["status"] = {
            "first_task_pct": _status(m["first_task_pct"], targets.get("first_task_pct")),
            "completion_pct": _status(m["completion_pct"], targets.get("completion_pct")),
            "median_login_to_task_days": _status(m["median_login_to_task_days"], targets.get("median_login_to_task_days"), True),
        }
        cohorts.append(m)
    total = _metrics(students, viewed)
    try:
        wau = an.engagement_section(students, raw, now)["wau"]
    except Exception:  # noqa: BLE001
        wau = None
    total["weekly_active"] = wau
    total["status"] = {
        "first_task_pct": _status(total["first_task_pct"], targets.get("first_task_pct")),
        "completion_pct": _status(total["completion_pct"], targets.get("completion_pct")),
        "median_login_to_task_days": _status(total["median_login_to_task_days"], targets.get("median_login_to_task_days"), True),
    }

    # ── Experiment: reminded students vs holdout, same trigger, same outcome window ──
    sub_times: dict[int, list[datetime]] = defaultdict(list)
    for x in raw["submissions"]:
        t = an.parse_ts(x["submitted_at"])
        if t:
            sub_times[x["student_id"]].append(t)
    rem = await db.fetch_all(
        """SELECT r.student_id, r.trigger_key, r.status, datetime(MIN(r.created_at)) AS t0,
                  MAX(CASE WHEN r.clicked_at IS NOT NULL THEN 1 ELSE 0 END) AS clicked,
                  MAX(CASE WHEN el.opened_at IS NOT NULL THEN 1 ELSE 0 END) AS opened
           FROM engagement_reminders r LEFT JOIN email_logs el ON el.id = r.email_log_id
           WHERE r.status IN ('sent', 'suppressed') AND (r.status = 'sent' OR r.reason = 'holdout')
             AND r.dedupe_key NOT LIKE 'manual:%'
           GROUP BY r.student_id, r.trigger_key, r.status""")
    exp: dict[str, dict] = {}
    for r in rem:
        s = by_id.get(r["student_id"])
        t0 = an.parse_ts(r["t0"])
        if not s or not t0 or r["trigger_key"] == "internship_completed":
            continue
        arm = "treated" if r["status"] == "sent" else "holdout"
        e = exp.setdefault(r["trigger_key"], {"treated": {"n": 0, "converted": 0, "clicked": 0, "opened": 0},
                                              "holdout": {"n": 0, "converted": 0}})
        e[arm]["n"] += 1
        e[arm]["converted"] += 1 if _outcome(r["trigger_key"], s, t0, sub_times.get(s["id"], [])) else 0
        if arm == "treated":
            e["treated"]["clicked"] += r["clicked"] or 0
            e["treated"]["opened"] += r["opened"] or 0
    experiments = []
    for trig, e in exp.items():
        tr, ho = e["treated"], e["holdout"]
        tr_rate, ho_rate = an.pct(tr["converted"], tr["n"]), an.pct(ho["converted"], ho["n"])
        experiments.append({
            "trigger": trig, "window_hours": OUTCOME_WINDOW_H,
            "treated": {**tr, "rate": tr_rate, "click_rate": an.pct(tr["clicked"], tr["n"]), "open_rate": an.pct(tr["opened"], tr["n"])},
            "holdout": {**ho, "rate": ho_rate},
            "lift_pts": round(tr_rate - ho_rate, 1) if ho["n"] and tr["n"] else None,
            "enough_data": tr["n"] >= MIN_SAMPLE and ho["n"] >= MIN_SAMPLE,
        })
    return {"group": group, "baseline": base, "targets": targets, "total": total, "cohorts": cohorts,
            "experiments": experiments, "min_sample": MIN_SAMPLE}
