"""
SkillMe — Student activation API (additive; nothing here is required by the core workflows).

  GET  /api/activation/me         onboarding state for the dashboard (flag-gated)
  POST /api/activation/events     records first_task_viewed
  POST /api/activation/support    "I need help" request
  GET  /r/{token}                 click tracking redirect for reminder emails (public)
  GET|POST /api/engagement/unsubscribe   one-click opt-out from reminder emails (public)
"""
from __future__ import annotations

import html
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from config import settings
from db.database import db
from middleware.student_auth import require_student
from services import activation_content as content
from services import activation_service as seg
from services import engagement_service as eng
from services.activation_events import record_event

router = APIRouter(prefix="/api/activation", tags=["activation"])
public_router = APIRouter(tags=["activation-public"])

SUPPORT_CATEGORIES = {
    "stuck_on_task": "I am stuck on the task",
    "login_access": "I cannot log in or access my dashboard",
    "submission_problem": "My submission is not working",
    "other": "Something else",
}
MAX_SUPPORT_PER_DAY = 3


async def _own(me: dict, student_id: int) -> None:
    if int(student_id) == int(me["id"]):
        return
    row = await db.fetch_one("SELECT email FROM students WHERE id = ?", (student_id,))
    if not row or (row["email"] or "").lower() != (me["email"] or "").lower():
        raise HTTPException(status_code=403, detail="You can only access your own internship.")


def _checklist(state: dict, viewed: bool) -> list[dict]:
    submitted = state["has_first_task"]
    return [
        {"key": "login", "label": "Log in to your dashboard", "done": True},
        {"key": "read", "label": "Read your Week 1 brief", "done": viewed or submitted,
         "hint": "It lists exactly what to build."},
        {"key": "build", "label": "Build it and share it on LinkedIn", "done": submitted,
         "hint": "A short post with your link is enough."},
        {"key": "submit", "label": "Paste your post link and submit", "done": submitted,
         "hint": "Use the Tasks tab."},
    ]


@router.get("/me", summary="Onboarding state for the student dashboard")
async def activation_me(student_id: int = Query(...), batch_id: Optional[int] = Query(None),
                        me: dict = Depends(require_student)):
    await _own(me, student_id)
    cfg = await seg.get_config()
    if not cfg.get("student_ui"):
        return {"enabled": False}
    state = await seg.student_state(student_id, batch_id)
    if not state:
        return {"enabled": False}
    bid = state["batch_id"]
    stage = state["stage"]
    if stage == "never_logged_in":  # they are authenticated right now
        stage = "no_first_task"
    approved = state["approved"]
    last = max(approved) if approved else 0
    viewed = bool(await db.fetch_one(
        "SELECT 1 AS x FROM student_events WHERE student_id = ? AND COALESCE(batch_id,0) = COALESCE(?,0) AND event_type = 'first_task_viewed'",
        (student_id, bid)))
    open_req = bool(await db.fetch_one(
        "SELECT 1 AS x FROM support_requests WHERE student_id = ? AND status = 'open' LIMIT 1", (student_id,)))
    out = {
        "enabled": True, "stage": stage, "stage_label": seg.STAGE_LABELS.get(stage),
        "batch_id": bid, "approved_weeks": approved, "total_weeks": 4,
        "support": {"open_request": open_req, "categories": SUPPORT_CATEGORIES},
    }
    if stage in ("no_first_task", "first_task_submitted"):
        out["checklist"] = _checklist(state, viewed)
        out["first_task"] = content.first_task_content(state["domain"], student_id)
        out["awaiting_review"] = stage == "first_task_submitted"
    elif stage and stage.startswith("stuck_week_"):
        nxt = min(last + 1, 4)
        wk = content.week_content(state["domain"], student_id, nxt)
        out["milestone"] = {"last_approved": last, "next_week": nxt, "next_title": wk["title"],
                            "time_label": wk["time_label"], "remaining": max(4 - last, 0),
                            "deliverables": wk["deliverables"],
                            "already_submitted": nxt in state["submitted_weeks"]}
    return out


class ViewEvent(BaseModel):
    student_id: int
    batch_id: Optional[int] = None
    event: Literal["first_task_viewed"]


@router.post("/events", summary="Record a first-task-viewed event")
async def activation_event(req: ViewEvent, me: dict = Depends(require_student)):
    await _own(me, req.student_id)
    state = await seg.student_state(req.student_id, req.batch_id)
    if not state:
        return {"recorded": False}
    created = await record_event("first_task_viewed", req.student_id, state["batch_id"], email=me["email"])
    return {"recorded": created}


class SupportRequest(BaseModel):
    student_id: int
    batch_id: Optional[int] = None
    category: Literal["stuck_on_task", "login_access", "submission_problem", "other"] = "other"
    message: str = Field("", max_length=1000)


@router.post("/support", summary="Ask for help")
async def activation_support(req: SupportRequest, me: dict = Depends(require_student)):
    await _own(me, req.student_id)
    recent = await db.fetch_one(
        "SELECT COUNT(*) AS n FROM support_requests WHERE student_id = ? AND created_at > datetime('now', '-1 day')",
        (req.student_id,))
    if int(recent["n"] or 0) >= MAX_SUPPORT_PER_DAY:
        raise HTTPException(status_code=429, detail="You have sent several requests today. We will reply soon.")
    state = await seg.student_state(req.student_id, req.batch_id)
    bid = state["batch_id"] if state else req.batch_id
    rid = await db.insert(
        "INSERT INTO support_requests (student_id, batch_id, category, message) VALUES (?, ?, ?, ?)",
        (req.student_id, bid, req.category, req.message.strip()))
    await record_event("support_requested", req.student_id, bid, email=me["email"], discriminator=rid,
                       meta={"category": req.category})
    return {"status": "received", "id": rid,
            "message": "Thanks. Our team will email you at " + me["email"] + " shortly."}


# ── Public: click tracking and unsubscribe ───────────────────────────────────

@public_router.get("/r/{token}", include_in_schema=False)
async def reminder_click(token: str):
    """Records the click (once) and sends the student to their dashboard. Unknown tokens just redirect."""
    try:
        await eng.register_click(token)
    except Exception:  # noqa: BLE001 — never block the student on tracking
        pass
    return RedirectResponse(f"{settings.frontend_url}/dashboard?src=reminder", status_code=302)


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#fafafa;color:#0a0a0a;
display:grid;place-items:center;min-height:100vh;margin:0}}.c{{max-width:420px;padding:32px;background:#fff;border:1px solid #e7e7ea;border-radius:14px}}
h1{{font-size:20px;margin:0 0 8px}}p{{color:#52525b;line-height:1.55;margin:0}}</style></head>
<body><div class="c"><h1>{html.escape(title)}</h1><p>{body}</p></div></body></html>""", status_code=status)


@public_router.get("/api/engagement/unsubscribe", include_in_schema=False)
async def unsubscribe_confirm(e: str = Query(""), s: str = Query("")):
    """GET only shows a confirm button: mail scanners prefetch links and must not unsubscribe anyone."""
    if not e or not eng.unsubscribe_valid(e, s):
        return _page("This link is not valid", "The unsubscribe link looks incomplete or has been changed.", 400)
    from urllib.parse import quote
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stop reminder emails</title><style>body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#fafafa;color:#0a0a0a;display:grid;place-items:center;min-height:100vh;margin:0}}
.c{{max-width:420px;padding:32px;background:#fff;border:1px solid #e7e7ea;border-radius:14px}}h1{{font-size:20px;margin:0 0 8px}}p{{color:#52525b;line-height:1.55;margin:0 0 18px}}
button{{background:#e5322d;color:#fff;border:0;border-radius:10px;padding:11px 18px;font-size:15px;font-weight:600;cursor:pointer}}</style></head>
<body><div class="c"><h1>Stop reminder emails?</h1><p>We will stop sending reminders to {html.escape(e)}. You will still get essential account emails such as login codes and task reviews.</p>
<form method="post" action="/api/engagement/unsubscribe?e={quote(e)}&amp;s={html.escape(s)}"><button type="submit">Yes, unsubscribe me</button></form></div></body></html>""")


@public_router.post("/api/engagement/unsubscribe", include_in_schema=False)
async def unsubscribe(e: str = Query(""), s: str = Query("")):
    if not e or not eng.unsubscribe_valid(e, s):
        return _page("This link is not valid", "The unsubscribe link looks incomplete or has been changed.", 400)
    await eng.opt_out(e)
    return _page("You are unsubscribed",
                 "We will stop sending you reminder emails. You will still receive essential account emails "
                 "such as login codes and task reviews.")
