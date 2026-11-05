"""
SkillMe — Analytics definitions and computation

ONE place where every dashboard number is defined. A single per-student rollup is built
from the raw tables and every section (overview, funnel, domains, acquisition, payments,
engagement) aggregates from that same list, so the sections cannot disagree.

Units
  student   = one `students` row (one per email + track). All student-level metrics count
              DISTINCT students.
  person    = lower(email) (one person can apply to several tracks).
  task      = one `submissions` row. Task-level numbers are always labelled "submissions".

Timestamps are stored in UTC. Date filters are entered as IST calendar dates and converted.
Rows flagged is_test (students or payments) are excluded unless include_test=True.
Nothing here writes to the database or rewrites history; gaps in old data are reported
as "legacy"/"unknown", never estimated.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta

TOTAL_WEEKS = 4
ELIGIBLE_WEEKS = 3             # approvals needed before the certificate can be bought
FIRST_STEP_ABANDON_MIN = 60    # an unpaid 'created' order older than this is abandoned
PENDING_ABANDON_HOURS = 24     # an unconfirmed 'pending' order older than this is abandoned
IST_OFFSET = timedelta(hours=5, minutes=30)

DEFINITIONS = {
    "applicant": "A student record: one application per email and track. People = distinct emails.",
    "enrolled": "Distinct students with an enrollment row (offer issued).",
    "started": "Enrolled and signed in to the dashboard at least once (first verified OTP).",
    "first_task": "At least one task submission (any status).",
    "weekly_milestone": "Student-level: students with that week approved. Task-level: approved submissions (labelled 'submissions').",
    "completed": "All 4 distinct weeks approved. Completed on the date of the last approval.",
    "certificate": "A certificates row on a valid enrollment. Split by how it was issued (payment / admin / legacy).",
    "eligible": "3 of 4 weeks approved, or payment unlocked by an admin (urgent request). Not dropped.",
    "checkout_initiated": "At least one real (non-test) payment order created.",
    "paid": "At least one successful, non-test payment.",
    "pending": "Latest order is authorized/attempted but not confirmed yet (and not yet old enough to be abandoned).",
    "failed": "Latest order failed (a failure reason is stored when Razorpay reports one).",
    "abandoned": f"Checkout opened but not paid: no success, and the order is older than {FIRST_STEP_ABANDON_MIN} min (created) or {PENDING_ABANDON_HOURS} h (pending). Derived, never stored.",
    "date_range": "Cohort filter: students who APPLIED in the range (IST). Every section uses the same cohort.",
}


# ──────────────────────────────────────────────
# Small helpers
# ──────────────────────────────────────────────

def parse_ts(v) -> datetime | None:
    """Parse the SQLite / ISO timestamps found in this DB (naive UTC)."""
    if not v:
        return None
    s = str(v).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:26] if "." in s else s[:19], fmt)
        except ValueError:
            continue
    return None


def ist_date_to_utc(d: str | None, end: bool = False) -> datetime | None:
    """'YYYY-MM-DD' (an IST calendar day) -> naive UTC datetime. `end` gives the exclusive end of that day."""
    if not d:
        return None
    try:
        day = datetime.strptime(d[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return day + (timedelta(days=1) if end else timedelta()) - IST_OFFSET


def pct(part: int | float, whole: int | float) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0


def days_between(a: datetime | None, b: datetime | None) -> float | None:
    if not a or not b:
        return None
    d = (b - a).total_seconds() / 86400
    return d if d >= 0 else None


def median(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.median(vals), 1) if vals else None


def p90(values: list[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    return round(vals[min(len(vals) - 1, int(len(vals) * 0.9))], 1) if vals else None


def timing(values: list[float], start: str, end: str) -> dict:
    vals = [v for v in values if v is not None]
    return {"from": start, "to": end, "n": len(vals), "median_days": median(vals), "p90_days": p90(vals)}


# ──────────────────────────────────────────────
# Loading
# ──────────────────────────────────────────────

STUDENT_SQL = """
SELECT s.id, s.first_name, s.last_name, s.email, s.domain, s.status AS student_status, s.college,
       s.referral_source, s.year_of_study, s.quiz_score, s.quiz_total, COALESCE(s.is_test, 0) AS is_test, datetime(s.created_at) AS applied_at,
       s.utm_source, s.utm_medium, s.utm_campaign, s.referral_code, s.landing_page, s.referrer,
       s.first_touch_source, s.last_touch_source, s.last_touch_campaign,
       COALESCE(s.attribution_captured, 0) AS attribution_captured,
       e.enrollments, e.enrolled_at, e.unlocked_at, e.active_enrollments, e.completed_enrollments,
       e.stored_completed_at,
       c.certs, c.cert_at, c.cert_via, c.valid_certs
FROM students s
LEFT JOIN (
    SELECT student_id, COUNT(*) AS enrollments, MIN(datetime(joined_at)) AS enrolled_at,
           MIN(datetime(payment_unlocked_at)) AS unlocked_at,
           SUM(CASE WHEN status != 'dropped' THEN 1 ELSE 0 END) AS active_enrollments,
           SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_enrollments,
           MAX(datetime(completed_at)) AS stored_completed_at
    FROM enrollments GROUP BY student_id) e ON e.student_id = s.id
LEFT JOIN (
    SELECT ce.student_id, COUNT(*) AS certs, MIN(datetime(ce.issued_at)) AS cert_at,
           MIN(COALESCE(ce.issued_via, 'legacy')) AS cert_via,
           SUM(CASE WHEN EXISTS (SELECT 1 FROM enrollments en WHERE en.student_id = ce.student_id
                                 AND en.batch_id = ce.batch_id AND en.status != 'dropped')
                    THEN 1 ELSE 0 END) AS valid_certs
    FROM certificates ce GROUP BY ce.student_id) c ON c.student_id = s.id
"""

SUBMISSION_SQL = """
SELECT student_id, batch_id, week, status, COALESCE(attempts, 1) AS attempts,
       datetime(submitted_at) AS submitted_at, reviewed_at AS reviewed_raw, datetime(reviewed_at) AS reviewed_at
FROM submissions"""

PAYMENT_SQL = """
SELECT id, student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, status,
       CASE WHEN COALESCE(is_test, 0) = 1 OR COALESCE(razorpay_payment_id, '') LIKE 'pay_test%'
                 OR COALESCE(razorpay_payment_id, '') LIKE 'pay_mock%' THEN 1 ELSE 0 END AS is_test,
       datetime(created_at) AS created_at, datetime(initiated_at) AS initiated_at, datetime(completed_at) AS completed_at,
       datetime(updated_at) AS updated_at, failure_code, failure_reason, discount_code, confirmed_via,
       last_touch_source, last_touch_campaign
FROM payments ORDER BY id"""

LOGIN_SQL = """
SELECT lower(email) AS email, datetime(COALESCE(verified_at, created_at)) AS at,
       CASE WHEN verified_at IS NULL THEN 1 ELSE 0 END AS legacy
FROM otp_tokens WHERE used = 1"""


async def load_raw(db) -> dict:
    """All source rows in ONE round trip (one HTTP pipeline call on Turso)."""
    students, subs, pays, logins, referrals = await db.fetch_batch([
        (STUDENT_SQL, ()), (SUBMISSION_SQL, ()), (PAYMENT_SQL, ()), (LOGIN_SQL, ()),
        ("SELECT status, COUNT(*) AS n FROM referral_conversions GROUP BY status", ()),
    ])
    return {"students": students, "submissions": subs, "payments": pays, "logins": logins, "referrals": referrals}


# ──────────────────────────────────────────────
# Rollup
# ──────────────────────────────────────────────

def derive_pay_state(orders: list[dict], now: datetime) -> tuple[str, bool]:
    """(state, legacy) from a student's real orders. State: none|initiated|pending|failed|abandoned|paid."""
    if not orders:
        return "none", False
    if any(o["status"] == "paid" for o in orders):
        return "paid", False
    last = orders[-1]
    if last["status"] == "failed":
        return "failed", False
    started = parse_ts(last["initiated_at"] or last["created_at"])
    legacy = not last["initiated_at"]
    age = (now - started) if started else timedelta(days=999)
    if last["status"] == "pending":
        return ("abandoned" if age > timedelta(hours=PENDING_ABANDON_HOURS) else "pending"), legacy
    return ("abandoned" if age > timedelta(minutes=FIRST_STEP_ABANDON_MIN) else "initiated"), legacy


def build_students(raw: dict, now: datetime | None = None) -> list[dict]:
    """One dict per student with every stage timestamp/flag. The only place metrics are derived."""
    from services.task_service import task_service
    from services.email_service import _domain_label

    now = now or datetime.utcnow()
    subs_by: dict[int, list[dict]] = defaultdict(list)
    for r in raw["submissions"]:
        subs_by[r["student_id"]].append(r)
    pays_by: dict[int, list[dict]] = defaultdict(list)
    for r in raw["payments"]:
        pays_by[r["student_id"]].append(r)
    logins_by: dict[str, list[datetime]] = defaultdict(list)
    for r in raw["logins"]:
        t = parse_ts(r["at"])
        if t:
            logins_by[r["email"]].append(t)

    out = []
    for r in raw["students"]:
        s = dict(r)
        domain_raw = (s["domain"] or "").strip()
        s["domain_key"] = task_service.normalize_domain_slug(domain_raw) if domain_raw else "unspecified"
        s["domain_label"] = _domain_label(s["domain_key"]) if domain_raw else "Unspecified"
        s["name"] = f"{s['first_name']} {s['last_name']}".strip()
        applied = parse_ts(s["applied_at"])
        enrolled = parse_ts(s["enrolled_at"])
        s["applied_ts"], s["enrolled_ts"] = applied, enrolled
        s["is_enrolled"] = bool(s["enrollments"])
        s["is_dropped"] = bool(s["enrollments"]) and not s["active_enrollments"]

        subs = subs_by.get(s["id"], [])
        approved = {}
        for x in subs:
            if x["status"] == "approved":
                approved[x["week"]] = parse_ts(x["reviewed_at"])
        reached = {x["week"] for x in subs}
        s["submissions"] = len(subs)
        s["weeks_reached"] = sorted(reached)
        s["weeks_approved_set"] = sorted(approved)
        s["weeks_approved"] = len(approved)
        s["approved_submissions"] = len(approved)
        times = sorted(t for t in approved.values() if t)
        s["first_submit_ts"] = min((parse_ts(x["submitted_at"]) for x in subs if x["submitted_at"]), default=None)
        s["has_first_task"] = bool(subs)
        s["is_completed"] = len(approved) >= TOTAL_WEEKS
        s["completed_ts"] = times[-1] if s["is_completed"] and times else None
        unlocked = parse_ts(s["unlocked_at"])
        third = times[ELIGIBLE_WEEKS - 1] if len(times) >= ELIGIBLE_WEEKS else None
        s["eligible_ts"] = min((t for t in (third, unlocked) if t), default=None)
        s["is_eligible"] = (len(approved) >= ELIGIBLE_WEEKS or bool(unlocked)) and not s["is_dropped"]
        s["stored_completed"] = bool(s["completed_enrollments"])

        email = (s["email"] or "").lower()
        # "Started" = first verified sign-in on/after enrollment; legacy rows hold the code-request time.
        logins = sorted(logins_by.get(email, []))
        after = [t for t in logins if not enrolled or t >= enrolled - timedelta(minutes=5)]
        s["first_login_ts"] = after[0] if (after and s["is_enrolled"]) else None
        s["is_started"] = s["first_login_ts"] is not None
        activity = [t for t in (logins[-1:] or []) ] + [parse_ts(x["submitted_at"]) for x in subs] + [enrolled]
        s["last_activity_ts"] = max((t for t in activity if t), default=applied)

        # Certificates
        s["has_cert"] = bool(s["certs"])
        s["cert_ts"] = parse_ts(s["cert_at"])

        # Payments: test orders are kept out of every real figure
        all_orders = pays_by.get(s["id"], [])
        real = [o for o in all_orders if not o["is_test"]]
        s["orders"] = real
        s["test_orders"] = [o for o in all_orders if o["is_test"]]
        paid = [o for o in real if o["status"] == "paid"]
        s["has_paid"] = bool(paid)
        s["paid_amount"] = sum(o["amount"] or 0 for o in paid)
        s["paid_ts"] = min((parse_ts(o["completed_at"] or o["updated_at"]) for o in paid), default=None)
        s["paid_legacy_ts"] = bool(paid) and not any(o["completed_at"] for o in paid)
        s["has_checkout"] = bool(real)
        s["pay_state"], s["pay_legacy"] = derive_pay_state(real, now)
        s["last_order_ts"] = parse_ts(real[-1]["initiated_at"] or real[-1]["created_at"]) if real else None
        s["failure_reason"] = real[-1]["failure_reason"] if real and real[-1]["status"] == "failed" else None
        s["has_test_payment"] = bool(s["test_orders"])

        # Attribution: tracked first touch, else "unknown (pre-tracking)" for rows from before capture existed
        if s["attribution_captured"]:
            s["source_key"] = (s["first_touch_source"] or s["utm_source"] or "direct").strip().lower()
            s["source_tracked"] = True
        else:
            s["source_key"] = "unknown (pre-tracking)"
            s["source_tracked"] = False
        s["campaign_key"] = (s["utm_campaign"] or "").strip().lower() or "(none)"
        s["self_reported"] = (s["referral_source"] or "").strip() or "Not answered"
        out.append(s)
    return out


# ──────────────────────────────────────────────
# Filtering
# ──────────────────────────────────────────────

def apply_filters(students: list[dict], *, date_from=None, date_to=None, domain=None,
                  source=None, campaign=None, include_test=False) -> list[dict]:
    start, end = ist_date_to_utc(date_from), ist_date_to_utc(date_to, end=True)
    out = []
    for s in students:
        if not include_test and s["is_test"]:
            continue
        if start and (not s["applied_ts"] or s["applied_ts"] < start):
            continue
        if end and (not s["applied_ts"] or s["applied_ts"] >= end):
            continue
        if domain and s["domain_key"] != domain:
            continue
        if source and s["source_key"] != source.lower():
            continue
        if campaign and s["campaign_key"] != campaign.lower():
            continue
        out.append(s)
    return out


# ──────────────────────────────────────────────
# Stage predicates (also used for drill-downs)
# ──────────────────────────────────────────────

STAGES = [
    ("applied", "Applied", lambda s: True),
    ("enrolled", "Enrolled", lambda s: s["is_enrolled"]),
    ("started", "First login", lambda s: s["is_started"]),
    ("first_task", "First task submitted", lambda s: s["has_first_task"]),
    ("week1", "Week 1 approved", lambda s: 1 in s["weeks_approved_set"]),
    ("week2", "Week 2 approved", lambda s: 2 in s["weeks_approved_set"]),
    ("week3", "Week 3 approved", lambda s: 3 in s["weeks_approved_set"]),
    ("completed", "Completed (4/4)", lambda s: s["is_completed"]),
]
REVENUE_STAGES = [
    ("eligible", "Eligible for payment", lambda s: s["is_eligible"]),
    ("checkout", "Checkout initiated", lambda s: s["is_eligible"] and s["has_checkout"]),
    ("paid", "Paid", lambda s: s["is_eligible"] and s["has_paid"]),
    ("certified", "Certificate issued after payment", lambda s: s["is_eligible"] and s["has_paid"] and s["has_cert"]),
]
DRILL_PREDICATES = {
    **{k: p for k, _, p in STAGES},
    **{k: p for k, _, p in REVENUE_STAGES},
    "certified_any": lambda s: s["has_cert"],
    "paid_any": lambda s: s["has_paid"],
    "eligible_unpaid": lambda s: s["is_eligible"] and not s["has_paid"],
    "eligible_no_checkout": lambda s: s["is_eligible"] and not s["has_paid"] and not s["has_checkout"],
    "pay_pending": lambda s: s["pay_state"] in ("initiated", "pending"),
    "pay_failed": lambda s: s["pay_state"] == "failed",
    "pay_abandoned": lambda s: s["pay_state"] == "abandoned",
    "never_logged_in": lambda s: s["is_enrolled"] and not s["is_dropped"] and not s["is_started"],
    "enrolled_no_task": lambda s: s["is_enrolled"] and not s["is_dropped"] and not s["has_first_task"],
    "cert_not_completed": lambda s: s["has_cert"] and not s["is_completed"],
    "cert_not_paid": lambda s: s["has_cert"] and not s["has_paid"],
}


def stage_funnel(students: list[dict], stages) -> list[dict]:
    rows, prev, top = [], None, None
    for key, label, pred in stages:
        n = sum(1 for s in students if pred(s))
        top = n if top is None else top
        rows.append({
            "key": key, "label": label, "count": n,
            "pct_of_top": pct(n, top),
            "step_conversion": pct(n, prev) if prev is not None else None,
            "drop_off": (prev - n) if prev is not None else None,
            "drop_off_pct": pct(prev - n, prev) if prev else None,
        })
        prev = n
    return rows


# ──────────────────────────────────────────────
# Sections
# ──────────────────────────────────────────────

def _group(students: list[dict], keyfn, labelfn=None) -> dict[str, dict]:
    groups: dict[str, dict] = {}
    for s in students:
        k = keyfn(s)
        g = groups.setdefault(k, {"key": k, "label": labelfn(s) if labelfn else k, "applications": 0,
                                  "enrolled": 0, "activated": 0, "first_task": 0, "completed": 0,
                                  "certified": 0, "paid": 0, "revenue_rupees": 0.0})
        g["applications"] += 1
        g["enrolled"] += s["is_enrolled"]
        g["activated"] += s["is_started"]
        g["first_task"] += s["has_first_task"]
        g["completed"] += s["is_completed"]
        g["certified"] += s["has_cert"]
        g["paid"] += s["has_paid"]
        g["revenue_rupees"] += s["paid_amount"] / 100
    for g in groups.values():
        g["activation_rate"] = pct(g["activated"], g["applications"])
        g["completion_rate"] = pct(g["completed"], g["applications"])
        g["paid_rate"] = pct(g["paid"], g["applications"])
    return groups


def overview(students, now) -> dict:
    week_ago = now - timedelta(days=7)
    people = {(s["email"] or "").lower() for s in students}
    active7 = [s for s in students if s["last_activity_ts"] and s["last_activity_ts"] >= week_ago and s["is_enrolled"]]
    return {
        "applicants": len(students),
        "unique_people": len(people),
        "enrolled": sum(s["is_enrolled"] for s in students),
        "active_7d": len(active7),
        "completed": sum(s["is_completed"] for s in students),
        "certificates": sum(s["has_cert"] for s in students),
        "paying_students": sum(s["has_paid"] for s in students),
        "revenue_rupees": sum(s["paid_amount"] for s in students) / 100,
        "eligible_unpaid": sum(1 for s in students if s["is_eligible"] and not s["has_paid"]),
    }


def domains_section(students) -> list[dict]:
    groups = _group(students, lambda s: s["domain_key"], lambda s: s["domain_label"])
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for s in students:
        by_domain[s["domain_key"]].append(s)
    for k, g in groups.items():
        sts = by_domain[k]
        reached = [sum(1 for s in sts if w in s["weeks_reached"]) for w in range(1, TOTAL_WEEKS + 1)]
        g["retention"] = [{"week": i + 1, "reached": n, "pct_of_week1": pct(n, reached[0])} for i, n in enumerate(reached)]
        g["completed_of_started_pct"] = pct(g["completed"], g["first_task"])
        # Reconciliation: why certified can differ from completed
        g["certified_not_completed"] = sum(1 for s in sts if s["has_cert"] and not s["is_completed"])
        g["completed_not_certified"] = sum(1 for s in sts if s["is_completed"] and not s["has_cert"])
    return sorted(groups.values(), key=lambda g: g["applications"], reverse=True)


def acquisition_section(students) -> dict:
    tracked = [s for s in students if s["source_tracked"]]
    return {
        "coverage": {
            "total": len(students), "tracked": len(tracked), "pre_tracking_unknown": len(students) - len(tracked),
            "tracked_pct": pct(len(tracked), len(students)),
            "note": "Applications before attribution tracking shipped have no recoverable source and are shown as 'unknown (pre-tracking)'.",
        },
        "sources": sorted(_group(students, lambda s: s["source_key"]).values(), key=lambda g: -g["applications"]),
        "campaigns": sorted(
            _group([s for s in students if s["campaign_key"] != "(none)"],
                   lambda s: f"{s['source_key']} / {s['campaign_key']}").values(),
            key=lambda g: -g["applications"]),
        "self_reported": sorted(_group(students, lambda s: s["self_reported"]).values(), key=lambda g: -g["applications"]),
        "mediums": sorted(_group([s for s in students if s["utm_medium"]], lambda s: s["utm_medium"].lower()).values(),
                          key=lambda g: -g["applications"]),
    }


def payments_section(students, raw_payments, now) -> dict:
    state = defaultdict(int)
    legacy_abandoned = 0
    for s in students:
        if s["has_checkout"] or s["has_paid"]:
            state[s["pay_state"]] += 1
            if s["pay_state"] == "abandoned" and s["pay_legacy"]:
                legacy_abandoned += 1
    paid_rows = [p for s in students for p in s["orders"] if p["status"] == "paid"]
    tiers: dict[int, int] = defaultdict(int)
    monthly: dict[str, dict] = {}
    for p in paid_rows:
        tiers[p["amount"] or 0] += 1
        t = parse_ts(p["completed_at"] or p["updated_at"])
        if t:
            m = monthly.setdefault(t.strftime("%Y-%m"), {"month": t.strftime("%Y-%m"), "orders": 0, "revenue_rupees": 0.0})
            m["orders"] += 1
            m["revenue_rupees"] += (p["amount"] or 0) / 100
    # Test students are excluded from `students`, but their payments must still show as excluded
    test_paid_all = [p for p in raw_payments if p["is_test"] and p["status"] == "paid"]
    order_status = defaultdict(int)
    for s in students:
        for o in s["orders"]:
            order_status[o["status"]] += 1

    def row(s):
        last = s["orders"][-1] if s["orders"] else None
        return {
            "student_id": s["id"], "name": s["name"], "email": s["email"], "domain": s["domain_label"],
            "weeks_approved": s["weeks_approved"], "state": s["pay_state"], "legacy": s["pay_legacy"],
            "orders": len(s["orders"]), "last_order_at": last and (last["initiated_at"] or last["created_at"]),
            "amount_rupees": (last["amount"] or 0) / 100 if last else None,
            "failure_reason": s["failure_reason"], "unlocked_by_admin": bool(s["unlocked_at"]),
        }

    unpaid = [s for s in students if s["is_eligible"] and not s["has_paid"]]
    total = sum(p["amount"] or 0 for p in paid_rows) / 100
    return {
        "lifecycle": {
            "eligible": sum(1 for s in students if s["is_eligible"]),
            "eligible_unpaid": len(unpaid),
            "eligible_never_started_checkout": sum(1 for s in unpaid if not s["has_checkout"]),
            "checkout_initiated": sum(1 for s in students if s["has_checkout"]),
            "pending": state["pending"] + state["initiated"],
            "paid": state["paid"],
            "failed": state["failed"],
            "abandoned": state["abandoned"],
            "abandoned_legacy_unknown": legacy_abandoned,
        },
        "orders_by_status": dict(order_status),
        "revenue": {
            "total_rupees": total, "paid_orders": len(paid_rows), "paying_students": state["paid"],
            "avg_order_rupees": round(total / len(paid_rows), 2) if paid_rows else 0,
            "tiers": [{"price_rupees": a / 100, "orders": n, "revenue_rupees": a * n / 100}
                      for a, n in sorted(tiers.items(), reverse=True)],
            "trend": sorted(monthly.values(), key=lambda m: m["month"]),
            "paid_date_note": "Month = payment confirmation date. Orders before lifecycle tracking use their last-update time.",
        },
        "excluded_test": {"paid_orders": len(test_paid_all), "rupees": sum(p["amount"] or 0 for p in test_paid_all) / 100},
        "recovery": {
            "eligible_unpaid": [row(s) for s in sorted(unpaid, key=lambda s: -s["weeks_approved"])][:100],
            "abandoned": [row(s) for s in students if s["pay_state"] == "abandoned"][:100],
            "failed": [row(s) for s in students if s["pay_state"] == "failed"][:100],
        },
    }


def engagement_section(students, raw, now, inactive_days=7) -> dict:
    ids = {s["id"] for s in students}
    emails = {(s["email"] or "").lower() for s in students}
    subs = [x for x in raw["submissions"] if x["student_id"] in ids]
    email_of = {s["id"]: (s["email"] or "").lower() for s in students}
    acts = [(x["email"], parse_ts(x["at"])) for x in raw["logins"] if x["email"] in emails]
    acts += [(email_of[x["student_id"]], parse_ts(x["submitted_at"])) for x in subs]
    acts = [(e, t) for e, t in acts if t]
    login_times = [parse_ts(x["at"]) for x in raw["logins"] if x["email"] in emails]
    login_times = [t for t in login_times if t]
    wk = now - timedelta(days=7)
    mo = now - timedelta(days=30)
    by_person = acts
    weekly = []
    for w in range(1, TOTAL_WEEKS + 1):
        ws = [x for x in subs if x["week"] == w]
        weekly.append({
            "week": w,
            "students_reached": len({x["student_id"] for x in ws}),
            "students_approved": len({x["student_id"] for x in ws if x["status"] == "approved"}),
            "submissions": len(ws),
            "approved_submissions": sum(1 for x in ws if x["status"] == "approved"),
            "rejected_submissions": sum(1 for x in ws if x["status"] == "rejected"),
            "pending_submissions": sum(1 for x in ws if x["status"] == "pending"),
            "avg_attempts": round(sum(x["attempts"] for x in ws) / len(ws), 2) if ws else None,
        })
    waits = []
    for x in subs:
        if x["status"] in ("approved", "rejected"):
            d = days_between(parse_ts(x["submitted_at"]), parse_ts(x["reviewed_at"]))
            if d is not None:
                waits.append(d * 24)
    cutoff = now - timedelta(days=inactive_days)
    inactive = [s for s in students if s["is_enrolled"] and not s["is_dropped"] and not s["is_completed"]
                and s["last_activity_ts"] and s["last_activity_ts"] < cutoff]
    inactive.sort(key=lambda s: s["last_activity_ts"])
    return {
        "wau": len({e for e, t in by_person if t >= wk}),
        "mau": len({e for e, t in by_person if t >= mo}),
        "logins_30d": sum(1 for t in login_times if t >= mo),
        "never_logged_in": sum(1 for s in students if DRILL_PREDICATES["never_logged_in"](s)),
        "enrolled_no_task": sum(1 for s in students if DRILL_PREDICATES["enrolled_no_task"](s)),
        "first_task_students": sum(s["has_first_task"] for s in students),
        "weekly": weekly,
        "task_level": {
            "submissions": len(subs),
            "approved_submissions": sum(1 for x in subs if x["status"] == "approved"),
            "rejected_submissions": sum(1 for x in subs if x["status"] == "rejected"),
            "pending_submissions": sum(1 for x in subs if x["status"] == "pending"),
            "unit": "submissions (task-level). One student can have up to 4 approved submissions.",
        },
        "review_wait": {"median_hours": median(waits), "p90_hours": p90(waits), "reviews": len(waits)},
        "inactive_days": inactive_days,
        "inactive_count": len(inactive),
        "inactive": [{
            "student_id": s["id"], "name": s["name"], "email": s["email"], "domain": s["domain_label"],
            "weeks_approved": s["weeks_approved"], "last_activity": s["last_activity_ts"].strftime("%Y-%m-%d"),
            "days_inactive": round((now - s["last_activity_ts"]).total_seconds() / 86400),
        } for s in inactive[:100]],
    }


QUIZ_BANDS = ("0-49%", "50-79%", "80-100%")


def _quiz_band(score, total):
    if not total:
        return None
    p = (score or 0) * 100 / total
    return "0-49%" if p < 50 else ("50-79%" if p < 80 else "80-100%")


def growth_section(students, now) -> dict:
    people = {(s["email"] or "").lower() for s in students}
    daily: dict[str, int] = defaultdict(int)
    monthly: dict[str, int] = defaultdict(int)
    cutoff = now - timedelta(days=30)
    for s in students:
        t = s["applied_ts"]
        if not t:
            continue
        local = t + IST_OFFSET
        monthly[local.strftime("%Y-%m")] += 1
        if t >= cutoff:
            daily[local.strftime("%Y-%m-%d")] += 1
    return {
        "unique_people": len(people), "total_applications": len(students),
        "multi_track_rate": pct(len(students) - len(people), len(people)),
        "daily_applications": [{"day": d, "count": n} for d, n in sorted(daily.items())],
        "monthly_applications": [{"month": m, "count": n} for m, n in sorted(monthly.items())[-12:]],
    }


def audience_section(students) -> dict:
    def ranked(groups, limit=None):
        rows = sorted(groups.values(), key=lambda g: (g["applications"], g["paid"]), reverse=True)
        return rows[:limit] if limit else rows
    colleges = _group([s for s in students if (s["college"] or "").strip()], lambda s: s["college"].strip().lower(),
                      lambda s: s["college"].strip())
    years = _group([s for s in students if (s["year_of_study"] or "").strip()], lambda s: s["year_of_study"].strip().lower(),
                   lambda s: s["year_of_study"].strip())
    quiz = _group([s for s in students if _quiz_band(s["quiz_score"], s["quiz_total"])],
                  lambda s: _quiz_band(s["quiz_score"], s["quiz_total"]))
    return {
        "colleges": ranked(colleges, 10), "years": ranked(years),
        "quiz_bands": [quiz.get(b) or {"key": b, "label": b, "applications": 0, "completed": 0, "paid": 0,
                                       "completion_rate": 0.0, "paid_rate": 0.0} for b in QUIZ_BANDS],
    }


def timings_section(students) -> list[dict]:
    def span(a, b):
        return [days_between(s[a], s[b]) for s in students]
    return [
        timing(span("applied_ts", "enrolled_ts"), "Application", "Enrollment"),
        timing(span("enrolled_ts", "first_login_ts"), "Enrollment", "First login"),
        timing(span("first_login_ts", "first_submit_ts"), "First login", "First task"),
        timing(span("enrolled_ts", "first_submit_ts"), "Enrollment", "First task"),
        timing(span("applied_ts", "first_submit_ts"), "Application", "First task"),
        timing(span("first_submit_ts", "completed_ts"), "First task", "Completion (4/4)"),
        timing(span("eligible_ts", "paid_ts"), "Eligible", "Payment"),
    ]


def validation_warnings(students, funnel, revenue_funnel, domains) -> list[dict]:
    w = []

    def warn(level, code, msg, n=None):
        w.append({"level": level, "code": code, "message": msg, "count": n})

    counts = {r["key"]: r["count"] for r in funnel}
    prev = None
    for r in funnel:
        if r["key"] not in ("week1", "week2", "week3") and prev is not None and r["count"] > prev["count"]:
            warn("error", "funnel_not_monotonic", f"'{r['label']}' ({r['count']}) exceeds '{prev['label']}' ({prev['count']}).")
        prev = r
    if counts.get("first_task", 0) > counts.get("enrolled", 0):
        warn("error", "task_without_enrollment", "Some students submitted tasks without an enrollment.")
    ce = sum(1 for s in students if DRILL_PREDICATES["cert_not_completed"](s))
    if ce:
        warn("info", "cert_before_completion", f"{ce} certificate(s) belong to students who have not completed all 4 weeks (the 3-of-4 payment rule or an admin issue). Not an error; shown in Domain performance as 'certified, not completed'.", ce)
    cn = sum(1 for s in students if DRILL_PREDICATES["cert_not_paid"](s))
    if cn:
        warn("warning", "cert_without_payment", f"{cn} certificate(s) have no real (non-test) payment: admin-issued, test-paid, or legacy.", cn)
    pe = sum(1 for s in students if s["has_paid"] and not s["is_eligible"])
    if pe:
        warn("warning", "paid_not_eligible", f"{pe} paying student(s) do not meet the eligibility rule by submission records.", pe)
    drift = sum(1 for s in students if s["stored_completed"] != s["is_completed"])
    if drift:
        warn("info", "stored_completion_drift", f"{drift} student(s) have a stored enrollment completion status that differs from approvals (older records were never marked completed; analytics derives completion from approvals).", drift)
    if sum(d["applications"] for d in domains) != len(students):
        warn("error", "domain_sum_mismatch", "Domain totals do not add up to total applicants.")
    unk = sum(1 for s in students if not s["source_tracked"])
    if students and unk:
        warn("info", "missing_attribution", f"{unk} of {len(students)} applicants ({pct(unk, len(students))}%) have no tracked acquisition source (applied before tracking).", unk)
    dup_orders = sum(1 for s in students if len([o for o in s["orders"] if o["status"] == "paid"]) > 1)
    if dup_orders:
        warn("warning", "multiple_paid_orders", f"{dup_orders} student(s) have more than one successful payment; check for double charges.", dup_orders)
    return w


def _referrals(raw: dict) -> dict:
    by = {r["status"]: r["n"] or 0 for r in raw.get("referrals", [])}
    enrolled = by.get("enrolled", 0)
    return {"clicked": sum(by.values()), "applied": by.get("applied", 0) + enrolled, "enrolled": enrolled}


def compute(raw: dict, students_all: list[dict], flt: dict, now: datetime | None = None, inactive_days: int = 7) -> dict:
    now = now or datetime.utcnow()
    students = apply_filters(students_all, **flt)
    funnel = stage_funnel(students, STAGES)
    rev_funnel = stage_funnel(students, REVENUE_STAGES)
    domains = domains_section(students)
    payments = payments_section(students, raw["payments"], now)
    return {
        "filters": {**flt, "timezone": "Asia/Kolkata", "generated_at": now.strftime("%Y-%m-%d %H:%M:%S") + " UTC"},
        "definitions": DEFINITIONS,
        "overview": overview(students, now),
        "funnel": {"learning": funnel, "revenue": rev_funnel, "timings": timings_section(students)},
        "domains": domains,
        "acquisition": {**acquisition_section(students), "referrals": _referrals(raw)},
        "growth": growth_section(students, now),
        "audience": audience_section(students),
        "payments": payments,
        "engagement": engagement_section(students, raw, now, inactive_days),
        "validation": validation_warnings(students, funnel, rev_funnel, domains),
        "options": {
            "domains": sorted({(s["domain_key"], s["domain_label"]) for s in students_all}),
            "sources": sorted({s["source_key"] for s in students_all}),
            "campaigns": sorted({s["campaign_key"] for s in students_all if s["campaign_key"] != "(none)"}),
        },
    }


def drilldown(students_all, flt, stage: str, page=1, limit=25, q=None) -> dict:
    pred = DRILL_PREDICATES.get(stage)
    if pred is None:
        raise KeyError(stage)
    rows = [s for s in apply_filters(students_all, **flt) if pred(s)]
    if q:
        needle = q.strip().lower()
        rows = [s for s in rows if needle in f"{s['name']} {s['email']} {s['domain_label']}".lower()]
    rows.sort(key=lambda s: s["applied_at"] or "", reverse=True)
    total = len(rows)
    limit = max(1, min(limit, 100))
    page = max(1, page)
    chunk = rows[(page - 1) * limit: page * limit]
    return {
        "stage": stage, "total": total, "page": page, "limit": limit, "total_pages": max(1, -(-total // limit)),
        "students": [{
            "id": s["id"], "name": s["name"], "email": s["email"], "domain": s["domain_label"],
            "applied_at": s["applied_at"], "enrolled": s["is_enrolled"], "started": s["is_started"],
            "weeks_approved": s["weeks_approved"], "completed": s["is_completed"], "certificate": s["has_cert"],
            "pay_state": s["pay_state"], "paid": s["has_paid"], "source": s["source_key"],
            "is_test": bool(s["is_test"]),
        } for s in chunk],
    }


# ──────────────────────────────────────────────
# Data quality (flags problems; changes nothing)
# ──────────────────────────────────────────────

async def data_quality(db, students_all: list[dict]) -> dict:
    progress, mixed_ts, orphan = await db.fetch_batch([
        ("SELECT student_id, COUNT(DISTINCT week) AS weeks FROM progress WHERE issues_completed > 0 GROUP BY student_id", ()),
        ("SELECT COUNT(*) AS n FROM submissions WHERE reviewed_at LIKE '%T%'", ()),
        ("""SELECT
              (SELECT COUNT(*) FROM certificates c WHERE NOT EXISTS (SELECT 1 FROM enrollments e WHERE e.student_id = c.student_id AND e.batch_id = c.batch_id)) AS certs,
              (SELECT COUNT(*) FROM payments p WHERE NOT EXISTS (SELECT 1 FROM enrollments e WHERE e.student_id = p.student_id AND e.batch_id = p.batch_id)) AS payments,
              (SELECT COUNT(*) FROM submissions x WHERE NOT EXISTS (SELECT 1 FROM enrollments e WHERE e.student_id = x.student_id AND e.batch_id = x.batch_id)) AS submissions""", ()),
    ])
    live = [s for s in students_all if not s["is_test"]]
    by_id = {s["id"]: s for s in live}

    def item(s, extra=None):
        return {"student_id": s["id"], "name": s["name"], "email": s["email"], "domain": s["domain_label"],
                "is_test": bool(s["is_test"]), **(extra or {})}

    checks = []

    def add(key, label, severity, items, note=None):
        checks.append({"key": key, "label": label, "severity": severity if items else "ok",
                       "count": len(items), "items": items[:50], "note": note})

    add("cert_no_real_payment", "Certificates with no real payment", "warning",
        [item(s, {"cert_via": s["cert_via"], "weeks_approved": s["weeks_approved"],
                  "test_payment": s["has_test_payment"]})
         for s in live if s["has_cert"] and not s["has_paid"]],
        "Admin-issued, linked to a test payment, or issued before issuance was recorded (legacy).")
    add("cert_not_completed", "Certificates before 4/4 completion", "info",
        [item(s, {"weeks_approved": s["weeks_approved"]}) for s in live if s["has_cert"] and not s["is_completed"]],
        "Expected under the 3-of-4 payment rule; listed for reconciliation.")
    add("cert_invalid_enrollment", "Certificates without a valid enrollment", "error",
        [item(s) for s in live if s["certs"] and (s["valid_certs"] or 0) < s["certs"]])
    add("test_payment_accounts", "Accounts linked to test payments (review: mark as test?)", "warning",
        [item(s, {"test_orders": len(s["test_orders"])}) for s in live if s["has_test_payment"] and not s["is_test"]],
        "Their test payments are already excluded from revenue. Mark the account as test to drop it from all counts.")
    add("missing_attribution", "Applicants with no tracked source", "info",
        [], "Pre-tracking applications cannot be attributed. See count below.")
    pre = sum(1 for s in live if not s["source_tracked"])
    checks[-1]["count"] = pre
    checks[-1]["severity"] = "info" if pre else "ok"
    checks[-1]["label"] = f"Applicants with no tracked source ({pct(pre, len(live))}% of all)"
    seen: dict[tuple, list] = defaultdict(list)
    for s in live:
        seen[((s["email"] or "").lower(), s["domain_key"])].append(s)
    add("duplicate_people", "Same person applied twice to the same track", "error",
        [item(v[0], {"records": len(v)}) for v in seen.values() if len(v) > 1])
    prog = {r["student_id"]: r["weeks"] for r in progress}
    add("progress_drift", "Progress table disagrees with approved submissions", "warning",
        [item(s, {"progress_weeks": prog.get(s["id"], 0), "approved_weeks": s["weeks_approved"]})
         for s in live if prog.get(s["id"], 0) != s["weeks_approved"]],
        "Payment unlocking reads `progress`, analytics reads `submissions`.")
    add("completion_not_stored", "Completed students whose enrollment is not marked completed", "info",
        [item(s) for s in live if s["is_completed"] and not s["stored_completed"]],
        "Enrollment completion is only recorded from now on; analytics derives it from approvals.")
    legacy_pending = [item(s) for s in live if s["pay_legacy"] and s["pay_state"] in ("abandoned", "pending")]
    add("legacy_pending_orders", "Unpaid orders from before lifecycle tracking", "info", legacy_pending,
        "Outcome unknown (no failure/abandon signal was recorded). Counted as abandoned, flagged legacy.")
    add("legacy_login_times", "Logins with request-time instead of verified time", "info", [],
        "Older logins record when the code was requested, not when it was entered.")
    add("mixed_timestamp_format", "Review timestamps in the old ISO format", "info", [],
        "Handled by the parser; harmless.")
    checks[-1]["count"] = (mixed_ts[0] or {}).get("n", 0) if mixed_ts else 0
    o = orphan[0] if orphan else {}
    add("orphans", "Certificates/payments/submissions with no matching enrollment", "error",
        [{"table": k, "count": v} for k, v in o.items() if v])
    return {"checks": checks, "problem_count": sum(1 for c in checks if c["severity"] in ("error", "warning"))}


# ──────────────────────────────────────────────
# Per-student journey
# ──────────────────────────────────────────────

async def journey(db, student_id: int) -> dict | None:
    student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    if not student:
        return None
    enrollments, subs, pays, certs, logins = await db.fetch_batch([
        ("SELECT * FROM enrollments WHERE student_id = ?", (student_id,)),
        ("SELECT * FROM submissions WHERE student_id = ? ORDER BY week", (student_id,)),
        ("SELECT * FROM payments WHERE student_id = ? ORDER BY id", (student_id,)),
        ("SELECT * FROM certificates WHERE student_id = ?", (student_id,)),
        ("""SELECT datetime(COALESCE(verified_at, created_at)) AS at, verified_at IS NULL AS legacy
            FROM otp_tokens WHERE lower(email) = lower(?) AND used = 1 ORDER BY id""", (student["email"],)),
    ])
    ev = [{"at": student["created_at"], "type": "applied", "label": f"Applied for {student['domain']}"}]
    for e in enrollments:
        ev.append({"at": e["joined_at"], "type": "enrolled", "label": f"Enrolled ({e['status']})"})
        if e.get("payment_unlocked_at"):
            ev.append({"at": e["payment_unlocked_at"], "type": "unlock", "label": "Payment unlocked by admin"})
        if e.get("completed_at"):
            ev.append({"at": e["completed_at"], "type": "completed", "label": "Internship completed (stored)"})
    for l in logins:
        ev.append({"at": l["at"], "type": "login", "label": "Signed in" + (" (code-request time, legacy)" if l["legacy"] else "")})
    for x in subs:
        ev.append({"at": x["submitted_at"], "type": "submission", "label": f"Week {x['week']} submitted (attempt {x.get('attempts') or 1})"})
        if x["reviewed_at"]:
            ev.append({"at": str(x["reviewed_at"]).replace("T", " ")[:19], "type": "review",
                       "label": f"Week {x['week']} {x['status']}"})
    for p in pays:
        flag = " [TEST]" if p.get("is_test") else ""
        ev.append({"at": p.get("initiated_at") or p["created_at"], "type": "checkout",
                   "label": f"Checkout started: order {p['razorpay_order_id']} ₹{(p['amount'] or 0) / 100:g}{flag}"})
        if p["status"] == "paid":
            ev.append({"at": p.get("completed_at") or p["updated_at"], "type": "paid",
                       "label": f"Paid {p['razorpay_payment_id']}{flag}"})
        elif p["status"] == "failed":
            ev.append({"at": p["updated_at"], "type": "failed", "label": f"Payment failed: {p.get('failure_reason') or 'no reason recorded'}"})
    for c in certs:
        ev.append({"at": c["issued_at"], "type": "certificate",
                   "label": f"Certificate {c['cert_id']} issued ({c.get('issued_via') or 'legacy'})"})
    ev.sort(key=lambda e: (str(e["at"] or ""), e["type"]))
    keep = ("id", "first_name", "last_name", "email", "domain", "college", "status", "is_test", "created_at",
            "utm_source", "utm_medium", "utm_campaign", "referral_code", "landing_page", "referrer",
            "first_touch_source", "last_touch_source", "last_touch_campaign", "attribution_captured", "referral_source")
    return {
        "student": {k: student.get(k) for k in keep},
        "timeline": ev,
        "payments": [{k: p.get(k) for k in ("id", "razorpay_order_id", "razorpay_payment_id", "amount", "status",
                                            "is_test", "initiated_at", "completed_at", "failure_reason", "confirmed_via")}
                     for p in pays],
    }
