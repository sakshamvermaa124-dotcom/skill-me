"""
SkillMe — Admin Student Recovery API (additive).

Everything is read-only on core tables. The only writes are to the activation tables:
student_events, engagement_settings, engagement_reminders, notification_preferences, support_requests.
"""
from __future__ import annotations

import json
import math
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from config import settings
from db.database import db
from middleware.auth import require_admin
from services import activation_backfill, activation_report
from services import activation_service as seg
from services import analytics_service as an
from services import engagement_service as eng

router = APIRouter(prefix="/api/admin/activation", tags=["admin-activation"])

PAGE_MAX = 100


def _iso(t):
    return t.isoformat() + "Z" if t else None


def _public(r: dict, last_rem: dict | None = None) -> dict:
    return {
        "id": r["id"], "batch_id": r["batch_id"], "name": r["name"], "email": r["email"],
        "domain": r["domain_key"], "domain_label": r["domain_label"],
        "enrolled_at": _iso(r["enrolled_ts"]), "stage": r["stage"], "stage_label": r["stage_label"],
        "weeks_approved": r["weeks_approved_set"], "current_milestone": r["current_milestone"],
        "last_activity_at": _iso(r["last_activity_ts"]), "days_idle": r["days_idle"],
        "inactive": r["inactive"], "eligibility": r["eligibility"], "holdout": r["holdout"],
        "is_test": r["is_test"], "recommended": eng.recommended_trigger(r),
        "last_reminder": last_rem,
    }


async def _last_reminders(ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    rows = await db.fetch_all(
        f"""SELECT r.student_id, r.trigger_key, r.status, r.step, r.created_at, r.clicked_at,
                   el.opened_at, el.delivered_at
            FROM engagement_reminders r LEFT JOIN email_logs el ON el.id = r.email_log_id
            WHERE r.student_id IN ({marks}) AND r.status IN ('sent','failed','dry_run')
            ORDER BY r.id DESC""", tuple(ids))
    out: dict[int, dict] = {}
    for x in rows:
        out.setdefault(x["student_id"], {
            "trigger": x["trigger_key"], "status": x["status"], "step": x["step"], "at": x["created_at"],
            "opened": bool(x["opened_at"]), "clicked": bool(x["clicked_at"])})
    return out


def _mode_info(cfg: dict) -> dict:
    mode, note = eng.effective_mode(cfg)
    return {"selected": cfg["mode"], "effective": mode, "note": note,
            "live_allowed": bool(settings.engagement_live_allowed)}


@router.get("/summary", summary="Stage counts, mode and last run")
async def summary(include_test: bool = False, _: str = Depends(require_admin)):
    rows, cfg = await seg.load_recovery_rows(include_test=include_test)
    s = seg.summarize(rows)
    last = await db.fetch_one("SELECT value FROM engagement_settings WHERE key = 'last_run'")
    open_support = await db.fetch_one("SELECT COUNT(*) AS n FROM support_requests WHERE status = 'open'")
    stats = await db.fetch_all(
        """SELECT status, COUNT(*) AS n FROM engagement_reminders
           WHERE created_at > datetime('now', '-1 day') GROUP BY status""")
    domains = sorted({(r["domain_key"], r["domain_label"]) for r in rows})
    return {
        **s, "inactive_days": cfg["inactive_days"], "mode": _mode_info(cfg), "last_run": json.loads(last["value"]) if last and last["value"] else None,
        "support_open": int(open_support["n"] or 0), "reminders_24h": {x["status"]: x["n"] for x in stats},
        "domains": [{"key": k, "label": l} for k, l in domains],
        "triggers": [{"key": k, "label": eng.TRIGGER_LABELS[k]} for k in eng.TRIGGERS],
    }


@router.get("/students", summary="Filterable recovery list")
async def students(
    stage: Optional[str] = None, domain: Optional[str] = None,
    enrolled_from: Optional[str] = None, enrolled_to: Optional[str] = None,
    activity: Optional[str] = Query(None, pattern="^(0-3|3-7|7-14|14\\+|never)$"),
    milestone: Optional[int] = Query(None, ge=1, le=4), eligibility: Optional[str] = Query(None, pattern="^(active|ended)$"),
    inactive: bool = False, q: Optional[str] = None, include_test: bool = False,
    page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=PAGE_MAX), _: str = Depends(require_admin),
):
    if stage and stage not in seg.STAGE_LABELS:
        raise HTTPException(status_code=400, detail="Unknown stage.")
    rows, _cfg = await seg.load_recovery_rows(include_test=include_test)
    out = seg.filter_rows(rows, stage=stage, domain=domain, enrolled_from=enrolled_from, enrolled_to=enrolled_to,
                          activity=activity, milestone=milestone, eligibility_=eligibility, inactive=inactive, q=q)
    # Open internships first (those are actionable), longest-idle first within each group
    out.sort(key=lambda r: (r["eligibility"] != "active", r["last_activity_ts"] is None, r["last_activity_ts"] or 0))
    total = len(out)
    chunk = out[(page - 1) * limit: page * limit]
    last = await _last_reminders([r["id"] for r in chunk])
    return {"total": total, "page": page, "limit": limit, "total_pages": max(1, math.ceil(total / limit)),
            "ids": [r["id"] for r in out][:2000], "students": [_public(r, last.get(r["id"])) for r in chunk]}


@router.get("/students/{student_id}", summary="One student's recovery detail")
async def student_detail(student_id: int, _: str = Depends(require_admin)):
    rows, cfg = await seg.load_recovery_rows(include_test=True)
    r = next((x for x in rows if x["id"] == student_id), None)
    if not r:
        raise HTTPException(status_code=404, detail="Student is not enrolled.")
    rems = await db.fetch_all(
        """SELECT r.id, r.trigger_key, r.step, r.status, r.reason, r.created_at, r.sent_at, r.clicked_at, el.opened_at
           FROM engagement_reminders r LEFT JOIN email_logs el ON el.id = r.email_log_id
           WHERE r.student_id = ? ORDER BY r.id DESC LIMIT 50""", (student_id,))
    events = await db.fetch_all(
        "SELECT event_type, occurred_at, source, meta FROM student_events WHERE student_id = ? ORDER BY occurred_at DESC LIMIT 100",
        (student_id,))
    support = await db.fetch_all(
        "SELECT id, category, message, status, admin_note, created_at, resolved_at FROM support_requests WHERE student_id = ? ORDER BY id DESC",
        (student_id,))
    try:
        journey = await an.journey(db, student_id)
    except Exception:  # noqa: BLE001
        journey = None
    rec = eng.recommended_trigger(r)
    return {"student": _public(r), "reminders": rems, "events": events, "support": support, "journey": journey,
            "recommended_label": eng.TRIGGER_LABELS.get(rec) if rec else None}


# ── Settings ─────────────────────────────────────────────────────────────────

class SettingsPatch(BaseModel):
    mode: Optional[str] = Field(None, pattern="^(off|dry_run|live)$")
    confirm_live: bool = False
    student_ui: Optional[bool] = None
    grace_days: Optional[int] = Field(None, ge=0, le=180)
    inactive_days: Optional[int] = Field(None, ge=1, le=90)
    frequency_cap_hours: Optional[int] = Field(None, ge=0, le=720)
    holdout_pct: Optional[int] = Field(None, ge=0, le=50)
    triggers: Optional[dict] = None
    targets: Optional[dict] = None


@router.get("/settings")
async def get_settings(_: str = Depends(require_admin)):
    cfg = await seg.get_config()
    return {"config": cfg, "mode": _mode_info(cfg)}


@router.put("/settings")
async def put_settings(body: SettingsPatch, _: str = Depends(require_admin)):
    patch = body.model_dump(exclude_none=True)
    confirm = patch.pop("confirm_live", False)
    if patch.get("mode") == "live":
        if not settings.engagement_live_allowed:
            raise HTTPException(status_code=409, detail="Live sending is blocked on this server (ENGAGEMENT_LIVE_ALLOWED is not enabled).")
        if not confirm:
            raise HTTPException(status_code=400, detail="Switching to Live requires explicit confirmation.")
    if "triggers" in patch:
        clean = {}
        for k, v in patch["triggers"].items():
            if k not in eng.TRIGGERS or not isinstance(v, dict):
                raise HTTPException(status_code=400, detail=f"Unknown trigger: {k}")
            item = {}
            if "enabled" in v:
                item["enabled"] = bool(v["enabled"])
            if "delays_h" in v:
                d = v["delays_h"]
                if not (isinstance(d, list) and 1 <= len(d) <= 5 and all(isinstance(x, (int, float)) and 0 <= x <= 24 * 60 for x in d)):
                    raise HTTPException(status_code=400, detail=f"Invalid delays for {k}.")
                item["delays_h"] = list(d)
            if "cooldown_days" in v:
                item["cooldown_days"] = max(1, min(int(v["cooldown_days"]), 90))
            clean[k] = item
        patch["triggers"] = clean
    cfg = await seg.save_config(patch)
    return {"config": cfg, "mode": _mode_info(cfg)}


# ── Sending ──────────────────────────────────────────────────────────────────

class PreviewReq(BaseModel):
    student_ids: list[int] = Field(..., min_length=1, max_length=500)
    override_ended: bool = False


@router.post("/preview", summary="Who would receive a reminder, and why others would not")
async def preview(req: PreviewReq, _: str = Depends(require_admin)):
    eligible, excluded, rows = await eng.evaluate_manual(req.student_ids, req.override_ended)
    cfg = await seg.get_config()
    sample = None
    if eligible:
        by = {r["id"]: r for r in rows}
        first = eligible[0]
        sample = {"student": first["name"], "trigger": first["trigger"], **eng.preview(by[first["student_id"]], first["trigger"], first["step"])}
    groups: dict[str, int] = {}
    for x in excluded:
        groups[x["reason"]] = groups.get(x["reason"], 0) + 1
    return {"mode": _mode_info(cfg), "eligible": eligible, "excluded": excluded, "excluded_by_reason": groups,
            "sample": sample, "ended_included": any(e["ended"] for e in eligible)}


class SendReq(PreviewReq):
    confirm: bool = False


@router.post("/send", summary="Send (or dry-run) the recommended reminder to selected students")
async def send(req: SendReq, background: BackgroundTasks, _: str = Depends(require_admin)):
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Sending requires explicit confirmation.")
    cfg = await seg.get_config()
    mode, note = eng.effective_mode(cfg)
    if mode == "live":
        background.add_task(eng.send_manual, req.student_ids, req.override_ended)
        return {"mode": mode, "queued": len(req.student_ids), "note": "Sending in the background. Check the Reminder log."}
    return await eng.send_manual(req.student_ids, req.override_ended)


@router.post("/run", summary="Run one automation pass now")
async def run_now(background: BackgroundTasks, _: str = Depends(require_admin)):
    cfg = await seg.get_config()
    mode, _note = eng.effective_mode(cfg)
    if mode == "live":
        background.add_task(eng.run_tick)
        return {"mode": mode, "queued": True, "note": "Running in the background."}
    return await eng.run_tick()


# ── Log, report, support, backfill ───────────────────────────────────────────

@router.get("/reminders")
async def reminders(status: Optional[str] = None, trigger: Optional[str] = None,
                    page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=PAGE_MAX), _: str = Depends(require_admin)):
    where, params = ["1=1"], []
    if status:
        where.append("r.status = ?"); params.append(status)
    if trigger:
        where.append("r.trigger_key = ?"); params.append(trigger)
    w = " AND ".join(where)
    total = (await db.fetch_one(f"SELECT COUNT(*) AS n FROM engagement_reminders r WHERE {w}", tuple(params)))["n"]
    rows = await db.fetch_all(
        f"""SELECT r.id, r.student_id, r.trigger_key, r.step, r.segment, r.status, r.reason, r.created_at, r.sent_at, r.clicked_at,
                   el.opened_at, s.first_name, s.last_name, s.email
            FROM engagement_reminders r LEFT JOIN email_logs el ON el.id = r.email_log_id
            LEFT JOIN students s ON s.id = r.student_id
            WHERE {w} ORDER BY r.id DESC LIMIT ? OFFSET ?""", (*params, limit, (page - 1) * limit))
    return {"total": total, "page": page, "limit": limit, "total_pages": max(1, math.ceil(total / limit)),
            "reminders": [{**x, "name": f"{x['first_name'] or ''} {x['last_name'] or ''}".strip()} for x in rows]}


@router.get("/report")
async def report(group: str = Query("month", pattern="^(week|month)$"), include_test: bool = False,
                 _: str = Depends(require_admin)):
    return await activation_report.build_report(group, include_test=include_test)


@router.get("/support")
async def support_list(status: Optional[str] = Query(None, pattern="^(open|resolved)$"), _: str = Depends(require_admin)):
    where, params = "", ()
    if status:
        where, params = "WHERE q.status = ?", (status,)
    rows = await db.fetch_all(
        f"""SELECT q.id, q.student_id, q.category, q.message, q.status, q.admin_note, q.created_at, q.resolved_at,
                   s.first_name, s.last_name, s.email, s.domain
            FROM support_requests q LEFT JOIN students s ON s.id = q.student_id {where}
            ORDER BY (q.status = 'open') DESC, q.id DESC LIMIT 200""", params)
    return {"requests": [{**x, "name": f"{x['first_name'] or ''} {x['last_name'] or ''}".strip()} for x in rows]}


class SupportPatch(BaseModel):
    status: str = Field(..., pattern="^(open|resolved)$")
    admin_note: Optional[str] = Field(None, max_length=1000)


@router.patch("/support/{request_id}")
async def support_update(request_id: int, body: SupportPatch, _: str = Depends(require_admin)):
    row = await db.fetch_one("SELECT id FROM support_requests WHERE id = ?", (request_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Request not found.")
    await db.execute(
        """UPDATE support_requests SET status = ?, admin_note = COALESCE(?, admin_note),
           resolved_at = CASE WHEN ? = 'resolved' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id = ?""",
        (body.status, body.admin_note, body.status, request_id))
    return {"status": body.status}


@router.post("/backfill", summary="Derive historical events (idempotent, read-only on core tables)")
async def backfill(_: str = Depends(require_admin)):
    return await activation_backfill.run()
