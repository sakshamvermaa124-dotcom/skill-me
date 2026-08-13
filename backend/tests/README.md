# SkillMe — Test Suite

A fast, self-contained regression test suite for the SkillMe backend.
Runs in **~5 seconds**, touches **zero production systems**, and catches regressions before they ship.

---

## Quick Start

```bash
cd backend
.\.venv\Scripts\python -m pytest tests/ -v
```

That is it. All 238 tests should pass with no setup beyond the existing virtual environment.

---

## Prerequisites

Make sure the test dependencies are installed (one-time):

```bash
.\.venv\Scripts\pip install pytest pytest-asyncio httpx
```

Or install everything from the test requirements file:

```bash
.\.venv\Scripts\pip install -r requirements-test.txt
```

---

## What the Tests Do

- **No live server needed** — the FastAPI app is tested in-process via `httpx.ASGITransport`
- **No production DB** — every test gets a fresh in-memory SQLite DB, wiped clean before each test
- **No external APIs** — GitHub, Razorpay, and Brevo (email) are all mocked

You can run the full suite safely at any time without touching production.

---

## After Making a Code Change — What to Run

### Made a small change? Run the full suite (fast enough):
```bash
.\.venv\Scripts\python -m pytest tests/ -v
```

### Changed auth logic?
```bash
.\.venv\Scripts\python -m pytest tests/auth/ -v
```

### Changed student application / status / progress?
```bash
.\.venv\Scripts\python -m pytest tests/students/ -v
```

### Changed admin endpoints (batches, enrollment, student management)?
```bash
.\.venv\Scripts\python -m pytest tests/admin/ -v
```

### Changed the certificate service or routes?
```bash
.\.venv\Scripts\python -m pytest tests/certificates/ -v
```

### Changed payment / Razorpay logic?
```bash
.\.venv\Scripts\python -m pytest tests/payments/ -v
```

### Changed the GitHub webhook handler?
```bash
.\.venv\Scripts\python -m pytest tests/webhooks/ -v
```

### Changed referral code / discount logic?
```bash
.\.venv\Scripts\python -m pytest tests/referrals/ -v
```

### Changed portfolio endpoint?
```bash
.\.venv\Scripts\python -m pytest tests/portfolio/ -v
```

### Changed routes in main.py (page routes, middleware)?
```bash
.\.venv\Scripts\python -m pytest tests/smoke/ -v
```

### Want to verify nothing critical is broken (fastest check)?
```bash
.\.venv\Scripts\python -m pytest tests/regression/ -v
```

---

## Run by Marker

Tests are tagged with markers. Use -m to run specific categories:

```bash
pytest -m smoke        # Page loads + health checks
pytest -m auth         # OTP login + session
pytest -m students     # Student application + progress
pytest -m admin        # All admin endpoints
pytest -m certificates # Certificate verify + issue + download
pytest -m payments     # Razorpay order + verify + status
pytest -m referrals    # Referral codes + stats + discounts
pytest -m portfolio    # Portfolio endpoint
pytest -m webhooks     # GitHub webhook events
pytest -m regression   # Critical end-to-end flows (run this always)
pytest -m edge         # Input validation + boundary + SQL injection
```

---

## Recommended Workflow After Any Change

1. **Edit** your code
2. **Run the specific module** tests for what you changed (fast feedback)
3. **Run regression tests** to make sure critical flows still work
4. **Run the full suite** before committing

```bash
# Step 2 — example: you changed routes/payments.py
.\.venv\Scripts\python -m pytest tests/payments/ -v

# Step 3 — always run regression
.\.venv\Scripts\python -m pytest tests/regression/ -v

# Step 4 — before committing
.\.venv\Scripts\python -m pytest tests/ -v
```

---

## Test Structure

```
tests/
├── conftest.py               <- shared fixtures, DB setup, service mocks
│
├── smoke/                    <- do all pages load? is the server healthy?
│   ├── test_pages_load.py
│   └── test_health.py
│
├── auth/                     <- OTP login, session cookies, logout
│   ├── test_otp_flow.py
│   └── test_session.py
│
├── students/                 <- apply, status check, progress tracking
│   ├── test_apply.py
│   └── test_progress.py
│
├── admin/                    <- batch CRUD, enrollment, student mgmt, stats
│   ├── test_batch_crud.py
│   ├── test_enrollment.py
│   ├── test_student_mgmt.py
│   └── test_stats.py
│
├── certificates/             <- verify, issue (admin), download (payment gate)
│   ├── test_verify.py
│   └── test_issue_cert.py
│
├── payments/                 <- Razorpay order creation, HMAC verify, status
│   └── test_payments.py
│
├── referrals/                <- code generation, stats, apply-with-referral
│   └── test_referral_flow.py
│
├── portfolio/                <- payment gate, public portfolio data
│   └── test_portfolio.py
│
├── webhooks/                 <- GitHub PR events, ping, unknown repos
│   └── test_github_webhook.py
│
├── edge_cases/               <- unicode, SQL injection, boundaries, malformed JSON
│   └── test_validation.py
│
└── regression/               <- critical end-to-end flows (must always pass)
    └── test_critical_flows.py
```

---

## Understanding Test Output

```
PASSED  <- working correctly
FAILED  <- something broke — read the assertion error
ERROR   <- test setup failed (usually an import or fixture issue)
```

A FAILED on a **bug-documenting test** (tests with "BUG:" in the docstring) is actually
**good news** — it means the bug has been fixed! Update the assertion to reflect the new
expected behavior.

---

## Known Bugs — Tests That Intentionally Capture Current Failures

Some tests document **real bugs** in the codebase. These tests PASS (they assert the buggy
behavior so they do not produce false alarms). When you fix a bug, update the test:

| Test | Bug | Fix In |
|---|---|---|
| `test_issue_cert_returns_500_due_to_bug` | KeyError 'issued_at' — service returns 'issued_on' | `routes/certificates.py:130` |
| `test_drop_student_updates_enrollments` | NameError: logger not defined | `routes/admin.py:563` — add import logging |
| `test_email_logs_filter_by_status_bug` | Ambiguous SQL column 'status' | `routes/admin.py:678` — use el.status |
| `test_verify_route_bug_documented` | /verify returns 404 | `main.py` — add "verify": "verify.html" to _PAGES |
| `test_pr_opened_for_tracked_repo_no_crash` | NOT NULL on submissions.issue_id | `services/batch_service.py:622` |

**When you fix one of these bugs:**
1. Run the relevant test — it will now show a different assertion error
2. Update the test assertion from the bug behavior to the correct (fixed) behavior
3. Add a comment: `# Bug fixed in commit <hash>`

---

## Adding New Tests

When you add a new feature or endpoint:

1. Create a file in the relevant directory (e.g. `tests/admin/test_new_feature.py`)
2. Add the `@pytest.mark.<category>` marker to the test class
3. Use existing fixtures from `conftest.py`:

| Fixture | What it gives you |
|---|---|
| `client` | httpx async test client (no auth) |
| `admin_headers` | `{"X-Admin-Key": "test-admin-key"}` |
| `test_student` | seeded student row (dict) |
| `test_batch` | seeded batch row (dict) |
| `enrolled_student` | student enrolled in test_batch |
| `paid_student` | student with completed payment |
| `student_headers` | `Authorization: Bearer <token>` header |
| `student_token` | raw JWT string (use to set cookies) |

```python
import pytest

@pytest.mark.admin
class TestMyNewFeature:
    async def test_happy_path(self, client, admin_headers):
        r = await client.get("/api/admin/my-new-endpoint", headers=admin_headers)
        assert r.status_code == 200
        assert "expected_field" in r.json()

    async def test_requires_auth(self, client):
        r = await client.get("/api/admin/my-new-endpoint")
        assert r.status_code == 403
```

Do not forget to add the marker name to `pytest.ini` under `markers =`.

---

## Cookie-Based Auth (Important!)

The `/api/auth/me` endpoint ONLY reads the `skillme_token` **cookie**.
It does NOT accept `Authorization: Bearer` headers.

If you need to test an authenticated /me call, set the cookie manually:

```python
async def test_get_me(self, client, student_token):
    client.cookies.set("skillme_token", student_token)
    r = await client.get("/api/auth/me")
    client.cookies.clear()
    assert r.status_code == 200
```

---

## CI Integration

To run in a CI pipeline (GitHub Actions, etc.), add this step:

```yaml
- name: Run test suite
  run: |
    cd backend
    pip install -r requirements-test.txt
    python -m pytest tests/ -v --tb=short
  env:
    ADMIN_API_KEY: test-admin-key
    JWT_SECRET_KEY: test-jwt-secret
    RAZORPAY_KEY_ID: rzp_test_dummy
    RAZORPAY_KEY_SECRET: test_secret
    EMAIL_ENABLED: "False"
    TURSO_DB_URL: ":memory:"
    TURSO_AUTH_TOKEN: ""
```

All env vars are set automatically by `conftest.py` via `os.environ.setdefault()`,
so CI works without any `.env` file.
