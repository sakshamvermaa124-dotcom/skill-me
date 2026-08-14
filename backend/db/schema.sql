-- SkillMe Database Schema
-- SQLite with strict typing

-- Students who have applied / are enrolled
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    github_username TEXT,
    linkedin_url TEXT,
    college TEXT,
    year_of_study TEXT,
    domain TEXT,                          -- e.g. 'web-dev', 'python', 'ml'
    motivation TEXT,
    referral_source TEXT,
    referred_by TEXT,
    status TEXT NOT NULL DEFAULT 'applied',  -- applied | shortlisted | enrolled | completed | dropped
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Batches — each batch is a group of students + a GitHub repo
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,              -- web-dev, python, react, etc.
    batch_number INTEGER NOT NULL,
    repo_name TEXT,                    -- GitHub repo name (e.g., web-dev-batch-1)
    status TEXT NOT NULL DEFAULT 'provisioning',  -- provisioning | active | completed | archived
    max_students INTEGER DEFAULT 30,
    start_date TEXT,
    end_date TEXT,
    auto_assign INTEGER DEFAULT 0,     -- 1 = auto-assign tasks each week
    weeks_assigned TEXT DEFAULT '[]',  -- JSON array of week numbers already assigned
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain, batch_number)
);

-- Enrollment — links students to batches (many-to-many)
CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'enrolled',  -- enrolled | active | completed | dropped
    github_invite_status TEXT DEFAULT 'pending',  -- pending | accepted | failed
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    UNIQUE(student_id, batch_id)
);

-- Issues — individual tasks assigned to students
CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    github_issue_number INTEGER,        -- The issue number on GitHub
    title TEXT NOT NULL,
    description TEXT,
    week_number INTEGER NOT NULL,       -- 1, 2, 3, or 4
    difficulty TEXT DEFAULT 'medium',   -- easy | medium | hard
    assigned_to INTEGER,                -- student_id
    status TEXT NOT NULL DEFAULT 'open',  -- open | assigned | in_progress | completed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    FOREIGN KEY (assigned_to) REFERENCES students(id)
);

-- Submissions — PR submissions for issues
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL,
    pr_url TEXT,
    pr_number INTEGER,
    status TEXT NOT NULL DEFAULT 'open',  -- open | tests_passed | tests_failed | merged | closed
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    merged_at TIMESTAMP,
    FOREIGN KEY (issue_id) REFERENCES issues(id),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id)
);

-- Progress — weekly aggregated progress per student per batch
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL,
    week INTEGER NOT NULL,              -- 1, 2, 3, or 4
    issues_assigned INTEGER DEFAULT 0,
    issues_completed INTEGER DEFAULT 0,
    prs_submitted INTEGER DEFAULT 0,
    prs_merged INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,            -- Calculated score for this week
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    UNIQUE(student_id, batch_id, week)
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_students_email ON students(email);
CREATE INDEX IF NOT EXISTS idx_students_github ON students(github_username);
CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_batch ON enrollments(batch_id);
CREATE INDEX IF NOT EXISTS idx_issues_batch ON issues(batch_id);
CREATE INDEX IF NOT EXISTS idx_issues_assigned ON issues(assigned_to);
CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_id);
CREATE INDEX IF NOT EXISTS idx_submissions_batch ON submissions(batch_id);

-- Certificates — issued on internship completion
CREATE TABLE IF NOT EXISTS certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL,
    cert_id TEXT NOT NULL UNIQUE,           -- e.g. SM-A1B2-C3D4-E5F6
    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    UNIQUE(student_id, batch_id)
);
CREATE INDEX IF NOT EXISTS idx_certs_student ON certificates(student_id);

-- Payments — Razorpay orders for certificate downloads
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL,
    razorpay_order_id TEXT UNIQUE,         -- rzp order id from Razorpay
    razorpay_payment_id TEXT,              -- filled on successful payment
    amount INTEGER NOT NULL,               -- amount in paise (24900 = ₹249)
    currency TEXT DEFAULT 'INR',
    status TEXT DEFAULT 'pending',         -- pending | paid | failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id)
);
CREATE INDEX IF NOT EXISTS idx_payments_student ON payments(student_id);

-- Email Logs — every email attempted, sent or failed
CREATE TABLE IF NOT EXISTS email_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_email TEXT NOT NULL,
    recipient_name  TEXT,
    email_type      TEXT NOT NULL,  -- application_confirmation | shortlisted | offer_letter | weekly_tasks | certificate_ready | test
    subject         TEXT NOT NULL,
    student_id      INTEGER,        -- NULL for non-student emails (e.g. test)
    batch_id        INTEGER,        -- NULL when not batch-related
    status          TEXT NOT NULL DEFAULT 'sent',  -- sent | failed
    error_message   TEXT,           -- populated on failure
    sent_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (batch_id)   REFERENCES batches(id)
);
CREATE INDEX IF NOT EXISTS idx_email_logs_recipient ON email_logs(recipient_email);
CREATE INDEX IF NOT EXISTS idx_email_logs_type      ON email_logs(email_type);
CREATE INDEX IF NOT EXISTS idx_email_logs_sent_at   ON email_logs(sent_at);

-- OTP Tokens — for student magic OTP login
CREATE TABLE IF NOT EXISTS otp_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL,
    otp_hash    TEXT NOT NULL,          -- bcrypt / sha256 hash of the 6-digit OTP
    expires_at  TIMESTAMP NOT NULL,
    used        INTEGER DEFAULT 0,      -- 0 = unused, 1 = consumed
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_otp_email ON otp_tokens(email);

-- Referral Codes — one per student
CREATE TABLE IF NOT EXISTS referral_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL UNIQUE,
    code        TEXT NOT NULL UNIQUE,   -- e.g. SKM-A1B2C3
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id)
);
CREATE INDEX IF NOT EXISTS idx_referral_codes_code ON referral_codes(code);

-- Referral Conversions — tracks referral → application → enrollment pipeline
CREATE TABLE IF NOT EXISTS referral_conversions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_student_id INTEGER NOT NULL,
    referred_student_id INTEGER,        -- NULL until they apply
    referred_email      TEXT NOT NULL,
    status              TEXT DEFAULT 'clicked',  -- clicked | applied | enrolled
    discount_applied    INTEGER DEFAULT 0,  -- paise discount given to referrer
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (referrer_student_id) REFERENCES students(id),
    FOREIGN KEY (referred_student_id) REFERENCES students(id)
);
CREATE INDEX IF NOT EXISTS idx_referral_conv_referrer ON referral_conversions(referrer_student_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- Monitoring & Automated QA System Tables
-- ═══════════════════════════════════════════════════════════════════════════

-- Monitoring alerts (synthetic test failures + real student errors + system issues)
CREATE TABLE IF NOT EXISTS monitor_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,           -- synthetic | real_student | system
    severity TEXT NOT NULL,             -- critical | warning | info
    category TEXT NOT NULL,             -- api_health | db_integrity | workflow_stuck | frontend_error | regression | e2e_test
    workflow TEXT,                      -- application | quiz | enrollment | github | certificate | lor | portfolio | verify | payment | auth | scheduler
    failed_step TEXT,                   -- exact step that failed
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    expected TEXT,
    actual TEXT,
    student_id INTEGER,                 -- NULL for synthetic tests
    student_email TEXT,
    api_response TEXT,
    error_details TEXT,                 -- stack trace, console error, etc.
    component TEXT,                     -- file/service to investigate
    is_regression INTEGER DEFAULT 0,    -- 1 = was working before
    is_resolved INTEGER DEFAULT 0,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_monitor_alerts_severity ON monitor_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_monitor_alerts_category ON monitor_alerts(category);
CREATE INDEX IF NOT EXISTS idx_monitor_alerts_created ON monitor_alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_monitor_alerts_resolved ON monitor_alerts(is_resolved);

-- Monitoring check results (health probe + synthetic test history)
CREATE TABLE IF NOT EXISTS monitor_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_name TEXT NOT NULL,           -- e.g. 'health_endpoint', 'db_connectivity', 'github_api'
    check_type TEXT NOT NULL,           -- probe | synthetic_e2e | db_integrity | stuck_detection
    status TEXT NOT NULL,               -- pass | fail | degraded
    response_time_ms INTEGER,
    details TEXT,                       -- JSON blob with check-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_monitor_checks_name ON monitor_checks(check_name);
CREATE INDEX IF NOT EXISTS idx_monitor_checks_created ON monitor_checks(created_at);

-- Frontend error reports from real student browser sessions
CREATE TABLE IF NOT EXISTS frontend_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page TEXT NOT NULL,                 -- quiz.html, dashboard.html, verify.html, etc.
    error_type TEXT NOT NULL,           -- js_error | network_error | ui_interaction
    message TEXT NOT NULL,
    stack_trace TEXT,
    url TEXT,
    user_agent TEXT,
    student_email TEXT,
    session_id TEXT,
    request_url TEXT,                   -- for network errors: the URL that failed
    request_status INTEGER,             -- for network errors: HTTP status code
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_frontend_errors_page ON frontend_errors(page);
CREATE INDEX IF NOT EXISTS idx_frontend_errors_created ON frontend_errors(created_at);
CREATE INDEX IF NOT EXISTS idx_frontend_errors_email ON frontend_errors(student_email);
