"""
SkillMe — Monitor API Routes
Endpoints for the monitoring dashboard, alert management, and frontend error ingestion.
"""

import json
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional

from middleware.auth import require_admin
from db.database import db
from services.monitor_service import (
    run_all_probes, run_smoke_tests, run_full_e2e_tests,
    check_db_integrity, detect_stuck_students, run_initial_audit,
    get_aggregate_errors, get_student_journey, SYNTHETIC_EMAIL,
)

logger = logging.getLogger("skillme.monitor.routes")
router = APIRouter(prefix="/api/monitor", tags=["monitor"])


# ── Request Models ────────────────────────────────────────────────────────────

class FrontendErrorReport(BaseModel):
    page: str = Field(..., max_length=200)
    error_type: str = Field(..., max_length=50)
    message: str = Field(..., max_length=2000)
    stack_trace: Optional[str] = Field(None, max_length=5000)
    url: Optional[str] = Field(None, max_length=500)
    user_agent: Optional[str] = Field(None, max_length=500)
    student_email: Optional[str] = Field(None, max_length=200)
    session_id: Optional[str] = Field(None, max_length=100)
    request_url: Optional[str] = Field(None, max_length=500)
    request_status: Optional[int] = None


class FrontendErrorBatch(BaseModel):
    errors: list[FrontendErrorReport] = Field(..., max_length=20)


# ── Public: Frontend error ingestion (no auth — used by student browsers) ────

@router.post("/errors", summary="Receive frontend error reports")
async def receive_frontend_errors(batch: FrontendErrorBatch, request: Request):
    """
    Public endpoint for the frontend error tracking SDK.
    Accepts a batch of error reports from student browsers.
    No authentication required — rate-limited by IP.
    """
    inserted = 0
    for err in batch.errors[:20]:  # Cap at 20 per request
        try:
            await db.insert(
                """INSERT INTO frontend_errors
                   (page, error_type, message, stack_trace, url, user_agent,
                    student_email, session_id, request_url, request_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (err.page, err.error_type, err.message, err.stack_trace,
                 err.url, err.user_agent, err.student_email, err.session_id,
                 err.request_url, err.request_status),
            )
            inserted += 1

            # Create an alert for critical frontend errors
            if err.error_type == "js_error":
                await db.insert(
                    """INSERT INTO monitor_alerts
                       (alert_type, severity, category, workflow, failed_step, title,
                        description, student_email, error_details, component)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("real_student", "warning", "frontend_error",
                     _page_to_workflow(err.page), err.error_type,
                     f"JS error on {err.page}: {err.message[:100]}",
                     f"Page: {err.page}\nURL: {err.url}\nMessage: {err.message}",
                     err.student_email, err.stack_trace,
                     err.page),
                )
        except Exception as e:
            logger.error(f"Failed to insert frontend error: {e}")

    return {"status": "ok", "inserted": inserted}


def _page_to_workflow(page: str) -> str:
    """Map a page name to its workflow category."""
    mapping = {
        "quiz.html": "quiz",
        "dashboard.html": "enrollment",
        "verify.html": "verify",
        "certificate.html": "certificate",
        "lor.html": "lor",
        "portfolio.html": "portfolio",
        "offer.html": "enrollment",
        "index.html": "application",
        "apply.html": "application",
    }
    return mapping.get(page, "unknown")


# ── Admin: System health overview ─────────────────────────────────────────────

@router.get("/status", summary="Overall system health status")
async def get_system_status(_: str = Depends(require_admin)):
    """Get a comprehensive system health summary."""
    # Latest check results per check_name
    try:
        latest_checks = await db.fetch_all(
            """SELECT mc1.check_name, mc1.check_type, mc1.status, mc1.response_time_ms,
                      mc1.details, mc1.created_at
               FROM monitor_checks mc1
               INNER JOIN (
                   SELECT check_name, MAX(id) as max_id
                   FROM monitor_checks GROUP BY check_name
               ) mc2 ON mc1.id = mc2.max_id
               ORDER BY mc1.check_name"""
        )
    except Exception:
        latest_checks = []

    # Active alert counts
    try:
        alert_counts = await db.fetch_all(
            """SELECT severity, COUNT(*) as cnt
               FROM monitor_alerts WHERE is_resolved = 0
               GROUP BY severity"""
        )
    except Exception:
        alert_counts = []

    # Recent frontend errors (last 24h)
    try:
        fe_count = await db.fetch_one(
            """SELECT COUNT(*) as cnt FROM frontend_errors
               WHERE created_at >= datetime('now', '-1 day')"""
        )
    except Exception:
        fe_count = {"cnt": 0}

    overall = "healthy"
    for check in latest_checks:
        if check.get("status") == "fail":
            overall = "critical"
            break
        elif check.get("status") == "degraded":
            overall = "degraded"

    return {
        "overall": overall,
        "latest_checks": latest_checks,
        "active_alerts": {r["severity"]: r["cnt"] for r in alert_counts},
        "frontend_errors_24h": fe_count["cnt"] if fe_count else 0,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Admin: Alerts ─────────────────────────────────────────────────────────────

@router.get("/alerts", summary="List all alerts")
async def list_alerts(
    severity: Optional[str] = None,
    category: Optional[str] = None,
    workflow: Optional[str] = None,
    limit: int = 50,
    _: str = Depends(require_admin),
):
    """List alerts, optionally filtered by severity/category/workflow."""
    query = "SELECT * FROM monitor_alerts WHERE 1=1"
    params = []

    if severity:
        query += " AND severity = ?"
        params.append(severity)
    if category:
        query += " AND category = ?"
        params.append(category)
    if workflow:
        query += " AND workflow = ?"
        params.append(workflow)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    alerts = await db.fetch_all(query, tuple(params))
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/alerts/active", summary="Active (unresolved) alerts")
async def active_alerts(_: str = Depends(require_admin)):
    """Get all unresolved alerts, ordered by severity then time."""
    alerts = await db.fetch_all(
        """SELECT * FROM monitor_alerts WHERE is_resolved = 0
           ORDER BY CASE severity
               WHEN 'critical' THEN 1
               WHEN 'warning' THEN 2
               WHEN 'info' THEN 3
           END, created_at DESC"""
    )
    return {"alerts": alerts, "count": len(alerts)}


@router.post("/alerts/{alert_id}/resolve", summary="Resolve an alert")
async def resolve_alert(alert_id: int, _: str = Depends(require_admin)):
    """Mark an alert as resolved."""
    await db.execute(
        "UPDATE monitor_alerts SET is_resolved = 1, resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
        (alert_id,),
    )
    return {"status": "resolved", "alert_id": alert_id}


# ── Admin: Check history ─────────────────────────────────────────────────────

@router.get("/checks", summary="Recent check results")
async def list_checks(
    check_name: Optional[str] = None,
    limit: int = 100,
    _: str = Depends(require_admin),
):
    """List recent monitoring check results."""
    if check_name:
        checks = await db.fetch_all(
            "SELECT * FROM monitor_checks WHERE check_name = ? ORDER BY created_at DESC LIMIT ?",
            (check_name, limit),
        )
    else:
        checks = await db.fetch_all(
            "SELECT * FROM monitor_checks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    return {"checks": checks, "count": len(checks)}


# ── Admin: Per-student journey ────────────────────────────────────────────────

@router.get("/student/{email}", summary="Per-student journey view")
async def student_journey(email: str, _: str = Depends(require_admin)):
    """Get complete journey + errors for a specific student."""
    journey = await get_student_journey(email)
    if "error" in journey:
        raise HTTPException(status_code=404, detail=journey["error"])
    return journey


# ── Admin: Stuck students ────────────────────────────────────────────────────

@router.get("/stuck-students", summary="Students stuck at any stage")
async def get_stuck_students(_: str = Depends(require_admin)):
    """Find students who appear stuck at any stage."""
    return await detect_stuck_students()


# ── Admin: Regression report ─────────────────────────────────────────────────

@router.get("/regression", summary="Regression report")
async def regression_report(_: str = Depends(require_admin)):
    """Get all regression alerts (checks that previously passed now failing)."""
    regressions = await db.fetch_all(
        """SELECT * FROM monitor_alerts WHERE is_regression = 1
           ORDER BY created_at DESC LIMIT 50"""
    )
    return {"regressions": regressions, "count": len(regressions)}


# ── Admin: Aggregate view ────────────────────────────────────────────────────

@router.get("/aggregate", summary="Aggregate error counts")
async def aggregate_errors(days: int = 7, _: str = Depends(require_admin)):
    """Get aggregate error/alert counts over the past N days."""
    return await get_aggregate_errors(days)


# ── Admin: Trigger all checks ────────────────────────────────────────────────

@router.post("/trigger", summary="Manually trigger all checks")
async def trigger_all_checks(_: str = Depends(require_admin)):
    """Run all monitoring checks immediately (post-deployment trigger)."""
    results = {}
    results["probes"] = await run_all_probes()
    results["smoke_tests"] = await run_smoke_tests()
    results["db_integrity"] = await check_db_integrity()
    results["stuck_students"] = await detect_stuck_students()
    return {"status": "completed", "results": results}


# ── Admin: One-time audit ────────────────────────────────────────────────────

@router.post("/audit", summary="Run one-time production data audit")
async def run_audit(_: str = Depends(require_admin)):
    """Run the one-time comprehensive audit of all existing production data."""
    audit = await run_initial_audit()
    return {"status": "completed", "audit": audit}


# ── Admin: Frontend error details ────────────────────────────────────────────

@router.get("/frontend-errors", summary="List frontend errors")
async def list_frontend_errors(
    page: Optional[str] = None,
    limit: int = 50,
    _: str = Depends(require_admin),
):
    """List frontend errors reported by real student browsers."""
    if page:
        errors = await db.fetch_all(
            "SELECT * FROM frontend_errors WHERE page = ? ORDER BY created_at DESC LIMIT ?",
            (page, limit),
        )
    else:
        errors = await db.fetch_all(
            "SELECT * FROM frontend_errors ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    return {"errors": errors, "count": len(errors)}
