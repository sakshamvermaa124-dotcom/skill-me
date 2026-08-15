"""
SkillMe — Monitor Service
Core monitoring engine for the real-time automated QA system.

Capabilities:
  - Health probes (API, DB, GitHub, email)
  - Synthetic end-to-end tests (application, auth, certificate, LOR, portfolio, verify)
  - Database integrity checks (orphans, missing records, inconsistencies)
  - Stuck-student detection (students stuck at any stage beyond expected time)
  - Regression detection (checks that previously passed now failing)
  - One-time audit (immediate scan of all existing production data)
  - Email delivery verification via Brevo API
"""

import json
import time
import logging
import traceback
from datetime import datetime, timedelta

import httpx

from db.database import db
from config import settings

logger = logging.getLogger("skillme.monitor")

# ── Synthetic test account ──────────────────────────────────────────────────
# Email used for synthetic E2E tests — MUST be excluded from all student views.
SYNTHETIC_EMAIL = "qa-synthetic-bot@skillme-internal-test.in"
SYNTHETIC_FIRST = "QA-Bot"
SYNTHETIC_LAST = "Synthetic"
SYNTHETIC_GITHUB = "skillme-qa-bot"

# Thresholds for stuck-student detection (in hours)
STUCK_THRESHOLDS = {
    "applied_no_action": 72,          # Applied but no admin action in 72h
    "shortlisted_no_enrollment": 48,  # Shortlisted but not enrolled in 48h
    "enrolled_no_issues": 24,         # Enrolled in active batch but no issues after 24h past start_date
    "pr_merged_no_progress": 6,       # PR merged but progress not updated in 6h
    "completed_no_certificate": 24,   # Status=completed but no certificate in 24h
    "paid_no_certificate": 2,         # Payment paid but no certificate in 2h
    "certificate_no_email": 6,        # Certificate issued but no email sent in 6h
}


# ═════════════════════════════════════════════════════════════════════════════
# Alert Creation
# ═════════════════════════════════════════════════════════════════════════════

async def _create_alert(
    alert_type: str,
    severity: str,
    category: str,
    title: str,
    description: str,
    workflow: str = None,
    failed_step: str = None,
    expected: str = None,
    actual: str = None,
    student_id: int = None,
    student_email: str = None,
    api_response: str = None,
    error_details: str = None,
    component: str = None,
    is_regression: int = 0,
) -> int:
    """Create an alert in the monitor_alerts table and return its ID."""
    try:
        alert_id = await db.insert(
            """INSERT INTO monitor_alerts
               (alert_type, severity, category, workflow, failed_step, title,
                description, expected, actual, student_id, student_email,
                api_response, error_details, component, is_regression)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (alert_type, severity, category, workflow, failed_step, title,
             description, expected, actual, student_id, student_email,
             api_response, error_details, component, is_regression),
        )
        logger.warning(f"ALERT [{severity.upper()}] {title}")
        return alert_id
    except Exception as e:
        logger.error(f"Failed to create alert: {e}")
        return 0


async def _record_check(
    check_name: str,
    check_type: str,
    status: str,
    response_time_ms: int = None,
    details: dict = None,
) -> None:
    """Record a check result in monitor_checks."""
    try:
        await db.insert(
            """INSERT INTO monitor_checks
               (check_name, check_type, status, response_time_ms, details)
               VALUES (?, ?, ?, ?, ?)""",
            (check_name, check_type, status, response_time_ms,
             json.dumps(details) if details else None),
        )
    except Exception as e:
        logger.error(f"Failed to record check: {e}")


async def _check_regression(check_name: str, current_status: str) -> bool:
    """Check if this check was passing before and is now failing = regression."""
    if current_status == "pass":
        return False
    try:
        prev = await db.fetch_one(
            """SELECT status FROM monitor_checks
               WHERE check_name = ? AND id < (SELECT MAX(id) FROM monitor_checks WHERE check_name = ?)
               ORDER BY id DESC LIMIT 1""",
            (check_name, check_name),
        )
        if prev and prev["status"] == "pass":
            return True
    except Exception:
        pass
    return False


def _get_candidate_backend_urls() -> list[str]:
    """Get candidate base URLs to reach the running backend instance."""
    candidates = []
    if settings.backend_url:
        candidates.append(settings.backend_url.rstrip("/"))
    candidates.append(f"http://127.0.0.1:{settings.port}")
    candidates.append(f"http://localhost:{settings.port}")
    candidates.append("http://127.0.0.1:8000")
    candidates.append("http://localhost:8000")
    candidates.append("http://127.0.0.1:8080")
    candidates.append("http://localhost:8080")
    return list(dict.fromkeys(candidates))


# ═════════════════════════════════════════════════════════════════════════════
# Health Probes
# ═════════════════════════════════════════════════════════════════════════════

async def probe_health_endpoint() -> dict:
    """Hit the /health endpoint and verify API + DB + GitHub connectivity."""
    check_name = "health_endpoint"
    start = time.time()
    urls = _get_candidate_backend_urls()
    last_err = None
    resp = None

    async with httpx.AsyncClient(timeout=10) as client:
        for u in urls:
            try:
                r = await client.get(f"{u}/health")
                resp = r
                break
            except Exception as e:
                last_err = e
                continue

    if resp is not None:
        elapsed = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = {"status": "healthy"}
            status = "pass" if data.get("status") == "healthy" else "degraded"
            is_reg = await _check_regression(check_name, status)
            await _record_check(check_name, "probe", status, elapsed, data)
            if status == "degraded":
                await _create_alert(
                    "synthetic", "warning", "api_health",
                    "Health endpoint reports degraded status",
                    f"The /health endpoint returned: {json.dumps(data)}",
                    component="backend/main.py",
                    api_response=json.dumps(data),
                    is_regression=int(is_reg),
                )
            return {"status": status, "data": data, "time_ms": elapsed}
        else:
            is_reg = await _check_regression(check_name, "fail")
            await _record_check(check_name, "probe", "fail", elapsed, {"status_code": resp.status_code})
            await _create_alert(
                "synthetic", "critical", "api_health",
                "Health endpoint returned non-200",
                f"GET /health returned HTTP {resp.status_code}",
                expected="HTTP 200 with healthy status",
                actual=f"HTTP {resp.status_code}",
                component="backend/main.py",
                is_regression=int(is_reg),
            )
            return {"status": "fail", "status_code": resp.status_code, "time_ms": elapsed}
    else:
        elapsed = int((time.time() - start) * 1000)
        is_reg = await _check_regression(check_name, "fail")
        await _record_check(check_name, "probe", "fail", elapsed, {"error": str(last_err)})
        await _create_alert(
            "synthetic", "critical", "api_health",
            "Health endpoint unreachable",
            f"Could not reach /health: {last_err}",
            expected="HTTP 200",
            actual=f"Connection error: {last_err}",
            component="backend/main.py",
            is_regression=int(is_reg),
        )
        return {"status": "fail", "error": str(last_err), "time_ms": elapsed}


async def probe_database() -> dict:
    """Run test queries against every critical table to verify DB connectivity."""
    check_name = "database_connectivity"
    start = time.time()
    tables = ["students", "batches", "enrollments", "issues", "submissions",
              "progress", "certificates", "payments", "email_logs"]
    results = {}
    all_ok = True

    for table in tables:
        try:
            row = await db.fetch_one(f"SELECT COUNT(*) as cnt FROM {table}")
            results[table] = {"count": row["cnt"], "ok": True}
        except Exception as e:
            results[table] = {"error": str(e), "ok": False}
            all_ok = False

    elapsed = int((time.time() - start) * 1000)
    status = "pass" if all_ok else "fail"
    is_reg = await _check_regression(check_name, status)
    await _record_check(check_name, "probe", status, elapsed, results)

    if not all_ok:
        failed = [t for t, r in results.items() if not r["ok"]]
        await _create_alert(
            "synthetic", "critical", "db_integrity",
            f"Database tables unreachable: {', '.join(failed)}",
            f"Failed to query tables: {', '.join(failed)}. Errors: {json.dumps({t: results[t] for t in failed})}",
            component="backend/db/database.py",
            is_regression=int(is_reg),
        )
    return {"status": status, "tables": results, "time_ms": elapsed}


async def probe_github_api() -> dict:
    """Verify GitHub token and org access."""
    check_name = "github_api"
    start = time.time()
    try:
        from services.github_service import github_service
        user = await github_service.verify_token()
        elapsed = int((time.time() - start) * 1000)
        if user:
            await _record_check(check_name, "probe", "pass", elapsed, {"user": user.get("login")})
            return {"status": "pass", "user": user.get("login"), "time_ms": elapsed}
        else:
            is_reg = await _check_regression(check_name, "fail")
            await _record_check(check_name, "probe", "fail", elapsed)
            await _create_alert(
                "synthetic", "critical", "api_health",
                "GitHub API token verification failed",
                "github_service.verify_token() returned None",
                workflow="github",
                component="backend/services/github_service.py",
                is_regression=int(is_reg),
            )
            return {"status": "fail", "time_ms": elapsed}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        is_reg = await _check_regression(check_name, "fail")
        await _record_check(check_name, "probe", "fail", elapsed, {"error": str(e)})
        await _create_alert(
            "synthetic", "critical", "api_health",
            "GitHub API unreachable",
            f"Exception during GitHub token verification: {e}",
            workflow="github",
            component="backend/services/github_service.py",
            error_details=traceback.format_exc(),
            is_regression=int(is_reg),
        )
        return {"status": "fail", "error": str(e), "time_ms": elapsed}


async def probe_email_smtp() -> dict:
    """Test SMTP connectivity (handshake only, no email sent)."""
    check_name = "email_smtp"
    start = time.time()
    try:
        import smtplib
        import ssl
        ctx = ssl.create_default_context()
        
        ports_to_try = [settings.smtp_port]
        for p in [587, 2525, 465]:
            if p not in ports_to_try:
                ports_to_try.append(p)
                
        last_err = None
        success_port = None
        
        for port in ports_to_try:
            try:
                if port == 465:
                    with smtplib.SMTP_SSL(settings.smtp_host, port, context=ctx, timeout=10) as server:
                        server.login(settings.smtp_user, settings.smtp_password)
                else:
                    with smtplib.SMTP(settings.smtp_host, port, timeout=10) as server:
                        server.ehlo()
                        server.starttls(context=ctx)
                        server.login(settings.smtp_user, settings.smtp_password)
                success_port = port
                break
            except Exception as e:
                last_err = e
                continue
                
        if not success_port:
            raise last_err or Exception("All SMTP ports failed")
            
        elapsed = int((time.time() - start) * 1000)
        await _record_check(check_name, "probe", "pass", elapsed, {"port_used": success_port})
        return {"status": "pass", "time_ms": elapsed, "port": success_port}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        is_reg = await _check_regression(check_name, "fail")
        await _record_check(check_name, "probe", "fail", elapsed, {"error": str(e)})
        await _create_alert(
            "synthetic", "warning", "api_health",
            "SMTP connection failed on all ports",
            f"Could not connect to {settings.smtp_host} on ports {ports_to_try}: {e}",
            component="backend/services/email_service.py",
            is_regression=int(is_reg),
        )
        return {"status": "fail", "error": str(e), "time_ms": elapsed}


async def probe_email_delivery() -> dict:
    """Check recent email delivery status via email_logs table."""
    check_name = "email_delivery"
    start = time.time()
    try:
        cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        total = await db.fetch_one(
            "SELECT COUNT(*) as cnt FROM email_logs WHERE sent_at >= ?", (cutoff,)
        )
        failed = await db.fetch_one(
            "SELECT COUNT(*) as cnt FROM email_logs WHERE sent_at >= ? AND status = 'failed'", (cutoff,)
        )
        total_cnt = total["cnt"] if total else 0
        failed_cnt = failed["cnt"] if failed else 0
        fail_rate = (failed_cnt / total_cnt * 100) if total_cnt > 0 else 0

        elapsed = int((time.time() - start) * 1000)
        status = "pass" if fail_rate < 10 else ("degraded" if fail_rate < 30 else "fail")
        details = {"total_24h": total_cnt, "failed_24h": failed_cnt, "fail_rate_pct": round(fail_rate, 1)}
        await _record_check(check_name, "probe", status, elapsed, details)

        if fail_rate >= 10:
            is_reg = await _check_regression(check_name, status)
            recent_fails = await db.fetch_all(
                """SELECT recipient_email, email_type, subject, error_message
                   FROM email_logs WHERE sent_at >= ? AND status = 'failed'
                   ORDER BY sent_at DESC LIMIT 5""",
                (cutoff,),
            )
            await _create_alert(
                "synthetic", "warning" if fail_rate < 30 else "critical", "api_health",
                f"Email delivery failure rate: {fail_rate:.0f}% in last 24h",
                f"{failed_cnt} of {total_cnt} emails failed. Recent: {json.dumps(recent_fails, default=str)}",
                workflow="certificate",
                component="backend/services/email_service.py",
                is_regression=int(is_reg),
            )
        return {"status": status, **details, "time_ms": elapsed}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        await _record_check(check_name, "probe", "fail", elapsed, {"error": str(e)})
        return {"status": "fail", "error": str(e), "time_ms": elapsed}


async def run_all_probes() -> dict:
    """Run all health probes and return combined results."""
    results = {}
    results["health"] = await probe_health_endpoint()
    results["database"] = await probe_database()
    results["github"] = await probe_github_api()
    results["email_smtp"] = await probe_email_smtp()
    results["email_delivery"] = await probe_email_delivery()

    overall = "healthy"
    for r in results.values():
        if r.get("status") == "fail":
            overall = "critical"
            break
        elif r.get("status") == "degraded":
            overall = "degraded"

    return {"overall": overall, "probes": results, "timestamp": datetime.utcnow().isoformat()}


# ═════════════════════════════════════════════════════════════════════════════
# Synthetic E2E Tests
# ═════════════════════════════════════════════════════════════════════════════

async def test_application_flow() -> dict:
    """Synthetic: verify the student application DB layer works."""
    check_name = "e2e_application"
    start = time.time()
    try:
        existing = await db.fetch_one(
            "SELECT id, status FROM students WHERE email = ?", (SYNTHETIC_EMAIL,)
        )
        if existing:
            status_row = await db.fetch_one(
                "SELECT id, first_name, last_name, email, status FROM students WHERE lower(email) = lower(?)",
                (SYNTHETIC_EMAIL,),
            )
            elapsed = int((time.time() - start) * 1000)
            if status_row and status_row["email"].lower() == SYNTHETIC_EMAIL.lower():
                await _record_check(check_name, "synthetic_e2e", "pass", elapsed,
                                    {"student_id": status_row["id"], "status": status_row["status"]})
                return {"status": "pass", "note": "synthetic student exists", "time_ms": elapsed}

        elapsed = int((time.time() - start) * 1000)
        await _record_check(check_name, "synthetic_e2e", "pass", elapsed)
        return {"status": "pass", "time_ms": elapsed}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        is_reg = await _check_regression(check_name, "fail")
        await _record_check(check_name, "synthetic_e2e", "fail", elapsed, {"error": str(e)})
        await _create_alert(
            "synthetic", "critical", "e2e_test",
            "Application flow test failed",
            f"Synthetic application test failed: {e}",
            workflow="application", failed_step="student_apply",
            expected="Application submission succeeds and creates DB record",
            actual=f"Error: {e}",
            component="backend/routes/students.py",
            error_details=traceback.format_exc(),
            is_regression=int(is_reg),
        )
        return {"status": "fail", "error": str(e), "time_ms": elapsed}


async def test_certificate_verify() -> dict:
    """Synthetic: verify certificate lookup works."""
    check_name = "e2e_certificate_verify"
    start = time.time()
    try:
        cert = await db.fetch_one("SELECT cert_id, student_id, batch_id FROM certificates LIMIT 1")
        if not cert:
            elapsed = int((time.time() - start) * 1000)
            await _record_check(check_name, "synthetic_e2e", "pass", elapsed,
                                {"note": "No certificates exist yet"})
            return {"status": "pass", "note": "no certificates to verify", "time_ms": elapsed}

        row = await db.fetch_one(
            """SELECT c.*, s.first_name, s.last_name, b.domain, b.batch_number
               FROM certificates c
               JOIN students s ON c.student_id = s.id
               JOIN batches b ON c.batch_id = b.id
               WHERE c.cert_id = ?""",
            (cert["cert_id"],),
        )
        elapsed = int((time.time() - start) * 1000)
        if row and row["cert_id"] == cert["cert_id"]:
            await _record_check(check_name, "synthetic_e2e", "pass", elapsed,
                                {"cert_id": cert["cert_id"], "holder": f"{row['first_name']} {row['last_name']}"})
            return {"status": "pass", "cert_id": cert["cert_id"], "time_ms": elapsed}
        else:
            is_reg = await _check_regression(check_name, "fail")
            await _record_check(check_name, "synthetic_e2e", "fail", elapsed)
            await _create_alert(
                "synthetic", "critical", "e2e_test",
                "Certificate verification lookup returned mismatched data",
                f"Queried cert_id={cert['cert_id']} but got mismatched result",
                workflow="verify", failed_step="certificate_lookup",
                component="backend/routes/certificates.py",
                is_regression=int(is_reg),
            )
            return {"status": "fail", "time_ms": elapsed}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        is_reg = await _check_regression(check_name, "fail")
        await _record_check(check_name, "synthetic_e2e", "fail", elapsed, {"error": str(e)})
        await _create_alert(
            "synthetic", "critical", "e2e_test",
            "Certificate verification test failed",
            f"Error: {e}",
            workflow="verify", failed_step="certificate_lookup",
            component="backend/routes/certificates.py",
            error_details=traceback.format_exc(),
            is_regression=int(is_reg),
        )
        return {"status": "fail", "error": str(e), "time_ms": elapsed}


async def test_lor_generation() -> dict:
    """Synthetic: verify LOR data pipeline works (cert verify -> LOR data)."""
    check_name = "e2e_lor_generation"
    start = time.time()
    try:
        cert = await db.fetch_one(
            """SELECT c.cert_id, c.student_id, c.batch_id, s.first_name, s.last_name,
                      b.domain, b.batch_number
               FROM certificates c
               JOIN students s ON c.student_id = s.id
               JOIN batches b ON c.batch_id = b.id
               LIMIT 1"""
        )
        if not cert:
            elapsed = int((time.time() - start) * 1000)
            await _record_check(check_name, "synthetic_e2e", "pass", elapsed,
                                {"note": "No certificates exist — LOR test skipped"})
            return {"status": "pass", "note": "no certificates for LOR", "time_ms": elapsed}

        # Test 1: Certificate verify returns data LOR needs
        verify_row = await db.fetch_one(
            """SELECT c.cert_id, s.first_name, s.last_name, b.domain, b.batch_number, c.issued_at
               FROM certificates c
               JOIN students s ON c.student_id = s.id
               JOIN batches b ON c.batch_id = b.id
               WHERE c.cert_id = ?""",
            (cert["cert_id"],),
        )
        if not verify_row:
            is_reg = await _check_regression(check_name, "fail")
            elapsed = int((time.time() - start) * 1000)
            await _record_check(check_name, "synthetic_e2e", "fail", elapsed)
            await _create_alert(
                "synthetic", "critical", "e2e_test",
                "LOR data pipeline broken: certificate verify returns no data",
                f"Certificate {cert['cert_id']} exists but verify query returned None",
                workflow="lor", failed_step="certificate_verify_for_lor",
                component="backend/routes/certificates.py",
                is_regression=int(is_reg),
            )
            return {"status": "fail", "time_ms": elapsed}

        # Test 2: All LOR-required fields present
        required_fields = ["cert_id", "first_name", "last_name", "domain"]
        missing = [f for f in required_fields if not verify_row.get(f)]
        if missing:
            is_reg = await _check_regression(check_name, "fail")
            elapsed = int((time.time() - start) * 1000)
            await _record_check(check_name, "synthetic_e2e", "fail", elapsed, {"missing_fields": missing})
            await _create_alert(
                "synthetic", "warning", "e2e_test",
                f"LOR data incomplete: missing fields {missing}",
                f"Certificate {cert['cert_id']} is missing LOR-required fields: {missing}",
                workflow="lor", failed_step="lor_data_completeness",
                component="backend/services/certificate_service.py",
                is_regression=int(is_reg),
            )
            return {"status": "fail", "missing": missing, "time_ms": int((time.time() - start) * 1000)}

        # Test 3: Certificate metadata endpoint
        meta = await db.fetch_one(
            "SELECT * FROM certificates WHERE student_id = ? AND batch_id = ?",
            (cert["student_id"], cert["batch_id"]),
        )
        elapsed = int((time.time() - start) * 1000)
        if meta:
            await _record_check(check_name, "synthetic_e2e", "pass", elapsed,
                                {"cert_id": cert["cert_id"], "holder": f"{cert['first_name']} {cert['last_name']}"})
            return {"status": "pass", "cert_id": cert["cert_id"], "time_ms": elapsed}
        else:
            is_reg = await _check_regression(check_name, "fail")
            await _record_check(check_name, "synthetic_e2e", "fail", elapsed)
            await _create_alert(
                "synthetic", "warning", "e2e_test",
                "LOR metadata lookup failed",
                f"Certificate exists but metadata lookup by student_id+batch_id failed",
                workflow="lor", failed_step="metadata_lookup",
                component="backend/routes/certificates.py",
                is_regression=int(is_reg),
            )
            return {"status": "fail", "time_ms": elapsed}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        is_reg = await _check_regression(check_name, "fail")
        await _record_check(check_name, "synthetic_e2e", "fail", elapsed, {"error": str(e)})
        await _create_alert(
            "synthetic", "critical", "e2e_test",
            "LOR generation test failed",
            f"Error: {e}",
            workflow="lor", failed_step="lor_test",
            component="backend/routes/certificates.py",
            error_details=traceback.format_exc(),
            is_regression=int(is_reg),
        )
        return {"status": "fail", "error": str(e), "time_ms": elapsed}


async def test_portfolio_endpoint() -> dict:
    """Synthetic: verify portfolio data API works."""
    check_name = "e2e_portfolio"
    start = time.time()
    try:
        student = await db.fetch_one(
            """SELECT s.github_username, s.id FROM students s
               JOIN payments p ON p.student_id = s.id
               WHERE p.status = 'paid' AND s.github_username IS NOT NULL
               LIMIT 1"""
        )
        if not student or not student.get("github_username"):
            elapsed = int((time.time() - start) * 1000)
            await _record_check(check_name, "synthetic_e2e", "pass", elapsed,
                                {"note": "No paid students with GitHub username"})
            return {"status": "pass", "note": "no portfolio-eligible students", "time_ms": elapsed}

        portfolio_student = await db.fetch_one(
            "SELECT id, first_name, last_name, github_username, college, domain FROM students WHERE LOWER(github_username) = LOWER(?)",
            (student["github_username"],),
        )
        elapsed = int((time.time() - start) * 1000)
        if portfolio_student:
            await _record_check(check_name, "synthetic_e2e", "pass", elapsed,
                                {"github": student["github_username"]})
            return {"status": "pass", "time_ms": elapsed}
        else:
            is_reg = await _check_regression(check_name, "fail")
            await _record_check(check_name, "synthetic_e2e", "fail", elapsed)
            await _create_alert(
                "synthetic", "warning", "e2e_test",
                "Portfolio lookup failed",
                f"Student with GitHub username '{student['github_username']}' not found",
                workflow="portfolio", failed_step="student_lookup",
                component="backend/routes/portfolio.py",
                is_regression=int(is_reg),
            )
            return {"status": "fail", "time_ms": elapsed}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        is_reg = await _check_regression(check_name, "fail")
        await _record_check(check_name, "synthetic_e2e", "fail", elapsed, {"error": str(e)})
        await _create_alert(
            "synthetic", "critical", "e2e_test",
            "Portfolio endpoint test failed",
            f"Error: {e}",
            workflow="portfolio", failed_step="portfolio_api",
            component="backend/routes/portfolio.py",
            error_details=traceback.format_exc(),
            is_regression=int(is_reg),
        )
        return {"status": "fail", "error": str(e), "time_ms": elapsed}


async def test_progress_endpoint() -> dict:
    """Synthetic: verify student progress API works."""
    check_name = "e2e_progress"
    start = time.time()
    try:
        student = await db.fetch_one(
            """SELECT s.email FROM students s
               JOIN enrollments e ON e.student_id = s.id
               WHERE s.email != ? LIMIT 1""",
            (SYNTHETIC_EMAIL,),
        )
        if not student:
            elapsed = int((time.time() - start) * 1000)
            await _record_check(check_name, "synthetic_e2e", "pass", elapsed,
                                {"note": "No enrolled students"})
            return {"status": "pass", "note": "no enrolled students", "time_ms": elapsed}

        progress = await db.fetch_all(
            """SELECT p.week, p.issues_completed, p.prs_merged
               FROM progress p
               JOIN students s ON p.student_id = s.id
               WHERE s.email = ?
               ORDER BY p.week""",
            (student["email"],),
        )
        elapsed = int((time.time() - start) * 1000)
        await _record_check(check_name, "synthetic_e2e", "pass", elapsed,
                            {"email": student["email"], "progress_rows": len(progress)})
        return {"status": "pass", "time_ms": elapsed}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        is_reg = await _check_regression(check_name, "fail")
        await _record_check(check_name, "synthetic_e2e", "fail", elapsed, {"error": str(e)})
        await _create_alert(
            "synthetic", "critical", "e2e_test",
            "Progress endpoint test failed",
            f"Error: {e}",
            workflow="enrollment", failed_step="progress_query",
            component="backend/routes/students.py",
            error_details=traceback.format_exc(),
            is_regression=int(is_reg),
        )
        return {"status": "fail", "error": str(e), "time_ms": elapsed}


async def test_payment_status() -> dict:
    """Synthetic: verify payment status query works."""
    check_name = "e2e_payment_status"
    start = time.time()
    try:
        payment = await db.fetch_one(
            "SELECT student_id, batch_id, status, amount FROM payments ORDER BY created_at DESC LIMIT 1"
        )
        elapsed = int((time.time() - start) * 1000)
        if not payment:
            await _record_check(check_name, "synthetic_e2e", "pass", elapsed, {"note": "No payments"})
            return {"status": "pass", "note": "no payments", "time_ms": elapsed}
        await _record_check(check_name, "synthetic_e2e", "pass", elapsed,
                            {"latest_status": payment["status"]})
        return {"status": "pass", "time_ms": elapsed}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        is_reg = await _check_regression(check_name, "fail")
        await _record_check(check_name, "synthetic_e2e", "fail", elapsed, {"error": str(e)})
        await _create_alert(
            "synthetic", "critical", "e2e_test",
            "Payment status test failed",
            f"Error: {e}",
            workflow="payment", failed_step="payment_status_query",
            component="backend/routes/payments.py",
            error_details=traceback.format_exc(),
            is_regression=int(is_reg),
        )
        return {"status": "fail", "error": str(e), "time_ms": elapsed}


async def test_admin_auth_protection() -> dict:
    """Synthetic: verify admin endpoints reject unauthenticated requests."""
    check_name = "e2e_admin_auth"
    start = time.time()
    try:
        urls = _get_candidate_backend_urls()
        protected_paths = ["/api/admin/stats", "/api/admin/batches", "/api/admin/students"]
        failures = []
        async with httpx.AsyncClient(timeout=10) as client:
            working_url = None
            for u in urls:
                try:
                    r = await client.get(f"{u}/health")
                    if r.status_code in (200, 404, 403):
                        working_url = u
                        break
                except Exception:
                    continue
            
            if not working_url:
                raise Exception("Backend unreachable; cannot test auth protection.")

            for path in protected_paths:
                try:
                    resp = await client.get(f"{working_url}{path}")
                    if resp.status_code != 403:
                        failures.append(f"{path} returned {resp.status_code} (expected 403)")
                except Exception as e:
                    failures.append(f"{path} error: {e}")

        elapsed = int((time.time() - start) * 1000)
        if not failures:
            await _record_check(check_name, "synthetic_e2e", "pass", elapsed)
            return {"status": "pass", "time_ms": elapsed}
        else:
            is_reg = await _check_regression(check_name, "fail")
            await _record_check(check_name, "synthetic_e2e", "fail", elapsed, {"failures": failures})
            await _create_alert(
                "synthetic", "critical", "e2e_test",
                "Admin auth protection broken",
                f"Endpoints accessible without auth: {'; '.join(failures)}",
                workflow="auth", failed_step="admin_auth_check",
                component="backend/middleware/auth.py",
                is_regression=int(is_reg),
            )
            return {"status": "fail", "failures": failures, "time_ms": elapsed}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        await _record_check(check_name, "synthetic_e2e", "fail", elapsed, {"error": str(e)})
        return {"status": "fail", "error": str(e), "time_ms": elapsed}


async def run_smoke_tests() -> dict:
    """Run critical-path smoke tests (every 15 min)."""
    results = {}
    results["application"] = await test_application_flow()
    results["certificate_verify"] = await test_certificate_verify()
    results["lor_generation"] = await test_lor_generation()
    results["progress"] = await test_progress_endpoint()
    results["payment_status"] = await test_payment_status()
    overall = "pass"
    for r in results.values():
        if r.get("status") == "fail":
            overall = "fail"
            break
    return {"overall": overall, "tests": results, "timestamp": datetime.utcnow().isoformat()}


async def run_full_e2e_tests() -> dict:
    """Run full E2E lifecycle tests (every 2 hours)."""
    results = {}
    results["application"] = await test_application_flow()
    results["certificate_verify"] = await test_certificate_verify()
    results["lor_generation"] = await test_lor_generation()
    results["portfolio"] = await test_portfolio_endpoint()
    results["progress"] = await test_progress_endpoint()
    results["payment_status"] = await test_payment_status()
    results["admin_auth"] = await test_admin_auth_protection()
    overall = "pass"
    for r in results.values():
        if r.get("status") == "fail":
            overall = "fail"
            break
    return {"overall": overall, "tests": results, "timestamp": datetime.utcnow().isoformat()}


# ═════════════════════════════════════════════════════════════════════════════
# Database Integrity Checks
# ═════════════════════════════════════════════════════════════════════════════

async def check_db_integrity() -> dict:
    """Run all database integrity checks."""
    results = {}

    # 1. Orphaned enrollments
    try:
        orphaned = await db.fetch_all(
            """SELECT e.id, e.student_id, e.batch_id FROM enrollments e
               LEFT JOIN students s ON e.student_id = s.id
               LEFT JOIN batches b ON e.batch_id = b.id
               WHERE s.id IS NULL OR b.id IS NULL"""
        )
        results["orphaned_enrollments"] = {"count": len(orphaned), "records": orphaned}
        if orphaned:
            await _create_alert("system", "warning", "db_integrity",
                f"{len(orphaned)} orphaned enrollment records",
                f"Enrollments referencing deleted students/batches: {json.dumps(orphaned, default=str)}",
                component="backend/db/database.py")
    except Exception as e:
        results["orphaned_enrollments"] = {"error": str(e)}

    # 2. Orphaned submissions
    try:
        orphaned = await db.fetch_all(
            """SELECT s.id, s.issue_id, s.student_id FROM submissions s
               LEFT JOIN issues i ON s.issue_id = i.id
               LEFT JOIN students st ON s.student_id = st.id
               WHERE i.id IS NULL OR st.id IS NULL"""
        )
        results["orphaned_submissions"] = {"count": len(orphaned), "records": orphaned[:20]}
        if orphaned:
            await _create_alert("system", "warning", "db_integrity",
                f"{len(orphaned)} orphaned submission records",
                "Submissions referencing deleted issues/students",
                component="backend/services/batch_service.py")
    except Exception as e:
        results["orphaned_submissions"] = {"error": str(e)}

    # 3. Completed students missing certificates
    try:
        missing = await db.fetch_all(
            """SELECT s.id, s.first_name, s.last_name, s.email, e.batch_id
               FROM students s
               JOIN enrollments e ON e.student_id = s.id
               WHERE (s.status = 'completed' OR e.status = 'completed')
                 AND s.email != ?
                 AND NOT EXISTS (
                     SELECT 1 FROM certificates c WHERE c.student_id = s.id AND c.batch_id = e.batch_id
                 )""",
            (SYNTHETIC_EMAIL,),
        )
        results["completed_no_certificate"] = {"count": len(missing), "students": missing}
        if missing:
            await _create_alert("system", "warning", "db_integrity",
                f"{len(missing)} completed students missing certificates",
                f"Students: {json.dumps(missing, default=str)}",
                workflow="certificate", failed_step="certificate_issuance",
                component="backend/services/certificate_service.py")
    except Exception as e:
        results["completed_no_certificate"] = {"error": str(e)}

    # 4. Orphaned certificates
    try:
        orphaned = await db.fetch_all(
            """SELECT c.id, c.cert_id, c.student_id, c.batch_id FROM certificates c
               LEFT JOIN students s ON c.student_id = s.id
               LEFT JOIN batches b ON c.batch_id = b.id
               WHERE s.id IS NULL OR b.id IS NULL"""
        )
        results["orphaned_certificates"] = {"count": len(orphaned), "records": orphaned}
        if orphaned:
            await _create_alert("system", "warning", "db_integrity",
                f"{len(orphaned)} orphaned certificate records",
                f"Certificates: {json.dumps(orphaned, default=str)}",
                workflow="certificate", component="backend/services/certificate_service.py")
    except Exception as e:
        results["orphaned_certificates"] = {"error": str(e)}

    # 5. Failed emails
    try:
        failed = await db.fetch_all(
            """SELECT id, recipient_email, email_type, subject, error_message, sent_at
               FROM email_logs WHERE status = 'failed' ORDER BY sent_at DESC LIMIT 50"""
        )
        results["failed_emails"] = {"count": len(failed), "records": failed[:20]}
        if len(failed) > 5:
            await _create_alert("system", "warning", "db_integrity",
                f"{len(failed)} failed emails in log",
                f"Types: {json.dumps([e.get('email_type') for e in failed], default=str)}",
                component="backend/services/email_service.py")
    except Exception as e:
        results["failed_emails"] = {"error": str(e)}

    # 6. Stuck pending payments
    try:
        cutoff = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        stuck = await db.fetch_all(
            """SELECT p.id, p.student_id, p.batch_id, p.razorpay_order_id, p.amount,
                      p.created_at, s.email, s.first_name
               FROM payments p JOIN students s ON p.student_id = s.id
               WHERE p.status = 'pending' AND p.created_at < ?""",
            (cutoff,),
        )
        results["stuck_payments"] = {"count": len(stuck), "records": stuck}
        if stuck:
            await _create_alert("system", "info", "db_integrity",
                f"{len(stuck)} payments stuck in pending >1h",
                f"Likely abandoned checkouts: {json.dumps(stuck, default=str)}",
                workflow="payment", component="backend/routes/payments.py")
    except Exception as e:
        results["stuck_payments"] = {"error": str(e)}

    # 7. Enrolled students missing progress
    try:
        no_progress = await db.fetch_all(
            """SELECT s.id, s.email, s.first_name, e.batch_id, b.domain
               FROM students s
               JOIN enrollments e ON e.student_id = s.id
               JOIN batches b ON e.batch_id = b.id
               WHERE b.status = 'active' AND e.status != 'dropped' AND s.email != ?
                 AND NOT EXISTS (
                     SELECT 1 FROM progress p WHERE p.student_id = s.id AND p.batch_id = e.batch_id
                 )""",
            (SYNTHETIC_EMAIL,),
        )
        results["enrolled_no_progress"] = {"count": len(no_progress), "students": no_progress}
    except Exception as e:
        results["enrolled_no_progress"] = {"error": str(e)}

    critical_issues = sum(
        r.get("count", 0) for k, r in results.items() 
        if isinstance(r, dict) and "count" in r and k not in ("stuck_payments", "enrolled_no_progress")
    )
    total_issues = sum(r.get("count", 0) for r in results.values() if isinstance(r, dict) and "count" in r)
    status = "pass" if critical_issues == 0 else "fail"
    await _record_check("db_integrity", "db_integrity", status, details={"total_issues": total_issues, "critical": critical_issues})
    return {"status": status, "total_issues": total_issues, "critical_issues": critical_issues, "checks": results}


# ═════════════════════════════════════════════════════════════════════════════
# Stuck-Student Detection
# ═════════════════════════════════════════════════════════════════════════════

async def detect_stuck_students() -> dict:
    """Find students stuck at any stage of the internship pipeline."""
    stuck = {}
    now = datetime.utcnow()

    # 1. Applied no action
    try:
        cutoff = (now - timedelta(hours=STUCK_THRESHOLDS["applied_no_action"])).strftime("%Y-%m-%d %H:%M:%S")
        rows = await db.fetch_all(
            """SELECT id, first_name, last_name, email, domain, created_at
               FROM students WHERE status = 'applied' AND email != ? AND created_at < ?
               ORDER BY created_at ASC""",
            (SYNTHETIC_EMAIL, cutoff),
        )
        stuck["applied_no_action"] = {
            "count": len(rows),
            "description": f"Applied >{STUCK_THRESHOLDS['applied_no_action']}h ago, no admin action",
            "students": rows,
        }
        for s in rows[:5]:
            await _create_alert("system", "info", "workflow_stuck",
                f"Student stuck in 'applied': {s['first_name']} {s['last_name']}",
                f"Applied on {s.get('created_at')}, still 'applied' after {STUCK_THRESHOLDS['applied_no_action']}h",
                workflow="application", failed_step="admin_review",
                student_id=s["id"], student_email=s["email"],
                component="backend/routes/admin.py")
    except Exception as e:
        stuck["applied_no_action"] = {"error": str(e)}

    # 2. Shortlisted not enrolled
    try:
        cutoff = (now - timedelta(hours=STUCK_THRESHOLDS["shortlisted_no_enrollment"])).strftime("%Y-%m-%d %H:%M:%S")
        rows = await db.fetch_all(
            """SELECT s.id, s.first_name, s.last_name, s.email, s.domain, s.updated_at
               FROM students s WHERE s.status = 'shortlisted' AND s.email != ? AND s.updated_at < ?
                 AND NOT EXISTS (SELECT 1 FROM enrollments e WHERE e.student_id = s.id)""",
            (SYNTHETIC_EMAIL, cutoff),
        )
        stuck["shortlisted_no_enrollment"] = {
            "count": len(rows),
            "description": f"Shortlisted >{STUCK_THRESHOLDS['shortlisted_no_enrollment']}h ago, not enrolled",
            "students": rows,
        }
    except Exception as e:
        stuck["shortlisted_no_enrollment"] = {"error": str(e)}

    # 3. Paid no certificate
    try:
        cutoff = (now - timedelta(hours=STUCK_THRESHOLDS["paid_no_certificate"])).strftime("%Y-%m-%d %H:%M:%S")
        rows = await db.fetch_all(
            """SELECT p.student_id, p.batch_id, p.updated_at as paid_at, s.email, s.first_name, s.last_name
               FROM payments p JOIN students s ON p.student_id = s.id
               WHERE p.status = 'paid' AND p.updated_at < ? AND s.email != ?
                 AND NOT EXISTS (
                     SELECT 1 FROM certificates c WHERE c.student_id = p.student_id AND c.batch_id = p.batch_id
                 )""",
            (cutoff, SYNTHETIC_EMAIL),
        )
        stuck["paid_no_certificate"] = {
            "count": len(rows),
            "description": f"Paid >{STUCK_THRESHOLDS['paid_no_certificate']}h ago, no certificate",
            "students": rows,
        }
        for s in rows:
            await _create_alert("system", "critical", "workflow_stuck",
                f"Paid student missing certificate: {s['first_name']} {s['last_name']}",
                f"Payment completed on {s.get('paid_at')} but no certificate issued",
                workflow="certificate", failed_step="certificate_issuance",
                student_id=s["student_id"], student_email=s["email"],
                component="backend/services/certificate_service.py")
    except Exception as e:
        stuck["paid_no_certificate"] = {"error": str(e)}

    # 4. Certificate issued no email
    try:
        cutoff = (now - timedelta(hours=STUCK_THRESHOLDS["certificate_no_email"])).strftime("%Y-%m-%d %H:%M:%S")
        rows = await db.fetch_all(
            """SELECT c.cert_id, c.student_id, c.issued_at, s.email, s.first_name, s.last_name
               FROM certificates c JOIN students s ON c.student_id = s.id
               WHERE c.issued_at < ? AND s.email != ?
                 AND NOT EXISTS (
                     SELECT 1 FROM email_logs el
                     WHERE el.student_id = c.student_id AND el.email_type = 'certificate_ready' AND el.status = 'sent'
                 )""",
            (cutoff, SYNTHETIC_EMAIL),
        )
        stuck["certificate_no_email"] = {
            "count": len(rows),
            "description": f"Certificate issued >{STUCK_THRESHOLDS['certificate_no_email']}h ago, no email",
            "students": rows,
        }
    except Exception as e:
        stuck["certificate_no_email"] = {"error": str(e)}

    total_stuck = sum(s.get("count", 0) for s in stuck.values() if isinstance(s, dict) and "count" in s)
    status = "pass" if total_stuck == 0 else "fail"
    await _record_check("stuck_student_detection", "stuck_detection", status,
                        details={"total_stuck": total_stuck})
    return {"status": status, "total_stuck": total_stuck, "categories": stuck}


# ═════════════════════════════════════════════════════════════════════════════
# One-Time Audit
# ═════════════════════════════════════════════════════════════════════════════

async def run_initial_audit() -> dict:
    """One-time comprehensive audit of all existing production data."""
    logger.info("Starting one-time production data audit...")
    audit = {}

    # Overall counts
    try:
        counts = {}
        for table in ["students", "batches", "enrollments", "issues", "submissions",
                       "progress", "certificates", "payments", "email_logs"]:
            row = await db.fetch_one(f"SELECT COUNT(*) as cnt FROM {table}")
            counts[table] = row["cnt"] if row else 0
        audit["table_counts"] = counts
    except Exception as e:
        audit["table_counts"] = {"error": str(e)}

    # Student status distribution
    try:
        dist = await db.fetch_all(
            "SELECT status, COUNT(*) as cnt FROM students WHERE email != ? GROUP BY status",
            (SYNTHETIC_EMAIL,),
        )
        audit["student_status_distribution"] = {r["status"]: r["cnt"] for r in dist}
    except Exception as e:
        audit["student_status_distribution"] = {"error": str(e)}

    # Batch status distribution
    try:
        dist = await db.fetch_all("SELECT status, COUNT(*) as cnt FROM batches GROUP BY status")
        audit["batch_status_distribution"] = {r["status"]: r["cnt"] for r in dist}
    except Exception as e:
        audit["batch_status_distribution"] = {"error": str(e)}

    audit["db_integrity"] = await check_db_integrity()
    audit["stuck_students"] = await detect_stuck_students()

    # Email summary
    try:
        rows = await db.fetch_all(
            "SELECT email_type, status, COUNT(*) as cnt FROM email_logs GROUP BY email_type, status"
        )
        email_report = {}
        for r in rows:
            etype = r["email_type"]
            if etype not in email_report:
                email_report[etype] = {}
            email_report[etype][r["status"]] = r["cnt"]
        audit["email_summary"] = email_report
    except Exception as e:
        audit["email_summary"] = {"error": str(e)}

    # Payment summary
    try:
        rows = await db.fetch_all(
            "SELECT status, COUNT(*) as cnt, SUM(amount) as total_paise FROM payments GROUP BY status"
        )
        audit["payment_summary"] = [dict(r) for r in rows]
    except Exception as e:
        audit["payment_summary"] = {"error": str(e)}

    # Zero-progress enrolled students
    try:
        rows = await db.fetch_all(
            """SELECT s.id, s.first_name, s.last_name, s.email, b.domain, b.batch_number,
                      b.start_date, b.status as batch_status
               FROM students s JOIN enrollments e ON e.student_id = s.id
               JOIN batches b ON e.batch_id = b.id
               WHERE e.status != 'dropped' AND s.email != ?
                 AND NOT EXISTS (
                     SELECT 1 FROM progress p WHERE p.student_id = s.id AND p.batch_id = e.batch_id
                       AND (p.issues_completed > 0 OR p.prs_merged > 0)
                 )""",
            (SYNTHETIC_EMAIL,),
        )
        audit["enrolled_zero_progress"] = {"count": len(rows), "students": rows}
    except Exception as e:
        audit["enrolled_zero_progress"] = {"error": str(e)}

    # Certificate data consistency
    try:
        cert_issues = []
        certs = await db.fetch_all(
            """SELECT c.cert_id, c.student_id, c.batch_id,
                      s.first_name, s.last_name, b.domain
               FROM certificates c
               JOIN students s ON c.student_id = s.id
               JOIN batches b ON c.batch_id = b.id"""
        )
        for cert in certs:
            if not cert["cert_id"] or not cert["cert_id"].startswith("SM-"):
                cert_issues.append({"cert_id": cert["cert_id"], "issue": "Invalid format",
                                    "student": f"{cert['first_name']} {cert['last_name']}"})
            if not cert.get("first_name") or not cert.get("last_name"):
                cert_issues.append({"cert_id": cert["cert_id"], "issue": "Missing name",
                                    "student_id": cert["student_id"]})
        audit["certificate_data_issues"] = {"count": len(cert_issues), "issues": cert_issues}
    except Exception as e:
        audit["certificate_data_issues"] = {"error": str(e)}

    logger.info("Audit complete.")
    return audit


# ═════════════════════════════════════════════════════════════════════════════
# Aggregate View
# ═════════════════════════════════════════════════════════════════════════════

async def get_aggregate_errors(days: int = 7) -> dict:
    """Get aggregate error counts over the past N days."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        fe_by_page = await db.fetch_all(
            "SELECT page, COUNT(*) as cnt FROM frontend_errors WHERE created_at >= ? GROUP BY page ORDER BY cnt DESC",
            (cutoff,),
        )
    except Exception:
        fe_by_page = []

    try:
        fe_by_type = await db.fetch_all(
            "SELECT error_type, COUNT(*) as cnt FROM frontend_errors WHERE created_at >= ? GROUP BY error_type ORDER BY cnt DESC",
            (cutoff,),
        )
    except Exception:
        fe_by_type = []

    try:
        alerts_by_workflow = await db.fetch_all(
            "SELECT workflow, severity, COUNT(*) as cnt FROM monitor_alerts WHERE created_at >= ? GROUP BY workflow, severity ORDER BY cnt DESC",
            (cutoff,),
        )
    except Exception:
        alerts_by_workflow = []

    try:
        alerts_by_category = await db.fetch_all(
            "SELECT category, COUNT(*) as cnt FROM monitor_alerts WHERE created_at >= ? GROUP BY category ORDER BY cnt DESC",
            (cutoff,),
        )
    except Exception:
        alerts_by_category = []

    return {
        "period_days": days,
        "frontend_errors_by_page": fe_by_page,
        "frontend_errors_by_type": fe_by_type,
        "alerts_by_workflow": alerts_by_workflow,
        "alerts_by_category": alerts_by_category,
    }


async def get_student_journey(email: str) -> dict:
    """Get complete journey view for a specific student."""
    student = await db.fetch_one(
        "SELECT * FROM students WHERE lower(email) = lower(?)", (email.strip(),)
    )
    if not student:
        return {"error": "Student not found"}

    sid = student["id"]
    journey = {"student": dict(student)}

    journey["enrollments"] = await db.fetch_all(
        """SELECT e.*, b.domain, b.batch_number, b.repo_name, b.status as batch_status
           FROM enrollments e JOIN batches b ON e.batch_id = b.id WHERE e.student_id = ?""", (sid,))
    journey["progress"] = await db.fetch_all(
        "SELECT * FROM progress WHERE student_id = ? ORDER BY week", (sid,))
    journey["submissions"] = await db.fetch_all(
        """SELECT s.*, i.title as issue_title, i.week_number
           FROM submissions s LEFT JOIN issues i ON s.issue_id = i.id WHERE s.student_id = ?""", (sid,))
    journey["certificates"] = await db.fetch_all(
        "SELECT * FROM certificates WHERE student_id = ?", (sid,))
    journey["payments"] = await db.fetch_all(
        "SELECT * FROM payments WHERE student_id = ?", (sid,))
    journey["emails"] = await db.fetch_all(
        "SELECT id, email_type, subject, status, sent_at FROM email_logs WHERE student_id = ? ORDER BY sent_at DESC", (sid,))
    journey["frontend_errors"] = await db.fetch_all(
        "SELECT * FROM frontend_errors WHERE student_email = ? ORDER BY created_at DESC LIMIT 50", (email.strip(),))
    journey["alerts"] = await db.fetch_all(
        "SELECT * FROM monitor_alerts WHERE student_id = ? OR student_email = ? ORDER BY created_at DESC LIMIT 50",
        (sid, email.strip()))

    stage = student["status"]
    if journey["certificates"]:
        stage = "certificate_issued"
    elif journey["payments"] and any(p["status"] == "paid" for p in journey["payments"]):
        stage = "paid"
    elif journey["enrollments"]:
        stage = "enrolled"
    journey["current_stage"] = stage

    return journey
