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

-- Batches — INTERNAL ONLY. There is no batch/cohort concept in the product any more:
-- every enrollment gets its own private row here (max_students = 1) and `batch_id`
-- elsewhere is just an opaque enrollment reference. Certificate IDs are a hash of
-- (student_id, batch_id), so never renumber, merge or reuse these rows.
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,              -- web-dev, python, react, etc.
    batch_number INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'provisioning',  -- provisioning | active | completed | archived
    max_students INTEGER DEFAULT 30,
    start_date TEXT,
    end_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain, batch_number)
);

-- Enrollment — one per student internship (re-enrolling after a drop reactivates the same row)
CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'enrolled',  -- enrolled | active | completed | dropped
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    payment_unlocked_at TIMESTAMP,        -- set when an admin fulfills an urgent request below 50% completion
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    UNIQUE(student_id, batch_id)
);

-- Submissions — a student's LinkedIn post submitted for a given week's task, pending admin review
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL,
    week INTEGER NOT NULL,              -- 1, 2, 3, or 4
    linkedin_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    admin_note TEXT,
    feedback TEXT,                      -- auto-generated per-task feedback sent on submission
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    UNIQUE(student_id, batch_id, week)
);

-- Progress — weekly aggregated progress per student per batch
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL,
    week INTEGER NOT NULL,              -- 1, 2, 3, or 4
    issues_completed INTEGER DEFAULT 0, -- tasks approved this week (0 or 1)
    score INTEGER DEFAULT 0,            -- Calculated score for this week
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id),
    UNIQUE(student_id, batch_id, week)
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_students_email ON students(email);
CREATE INDEX IF NOT EXISTS idx_students_github ON students(github_username);
-- Admin student list: newest-first pages, optionally filtered by status
CREATE INDEX IF NOT EXISTS idx_students_created ON students(created_at);
CREATE INDEX IF NOT EXISTS idx_students_status_created ON students(status, created_at);
CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_batch ON enrollments(batch_id);
CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_id);
CREATE INDEX IF NOT EXISTS idx_submissions_batch ON submissions(batch_id);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);

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
    amount INTEGER NOT NULL,               -- amount in paise (12900 = ₹129)
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
    email_type      TEXT NOT NULL,  -- application_confirmation | shortlisted | offer_letter | certificate_ready | test
    subject         TEXT NOT NULL,
    student_id      INTEGER,        -- NULL for non-student emails (e.g. test)
    batch_id        INTEGER,        -- NULL when not batch-related
    status          TEXT NOT NULL DEFAULT 'sent',  -- sent | failed
    error_message   TEXT,           -- populated on failure
    sent_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    message_tag     TEXT,           -- unique tag sent to Brevo, used to match webhook events back to this row
    delivered_at    TIMESTAMP,
    opened_at       TIMESTAMP,
    opened_count    INTEGER DEFAULT 0,
    clicked_at      TIMESTAMP,
    clicked_count   INTEGER DEFAULT 0,
    bounced_at      TIMESTAMP,
    bounce_type     TEXT,           -- soft | hard | blocked
    spam_reported_at TIMESTAMP,
    unsubscribed_at TIMESTAMP,
    last_event      TEXT,           -- most recent Brevo webhook event name
    last_event_at   TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (batch_id)   REFERENCES batches(id)
);
CREATE INDEX IF NOT EXISTS idx_email_logs_recipient ON email_logs(recipient_email);
CREATE INDEX IF NOT EXISTS idx_email_logs_type      ON email_logs(email_type);
CREATE INDEX IF NOT EXISTS idx_email_logs_sent_at   ON email_logs(sent_at);
-- idx_email_logs_tag is created via the migrations list in db/database.py instead of here —
-- this file's statements run unguarded before migrations, so referencing message_tag here would
-- crash startup on any database that pre-dates this column (ALTER TABLE migrations run after).

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

-- Urgent Requests — student-initiated 24h expedited certificate/LOR/portfolio processing
CREATE TABLE IF NOT EXISTS urgent_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL,
    request_type TEXT NOT NULL DEFAULT 'all',   -- certificate | lor | portfolio | all
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending',     -- pending | fulfilled | rejected
    admin_note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id)
);
CREATE INDEX IF NOT EXISTS idx_urgent_requests_student ON urgent_requests(student_id);
CREATE INDEX IF NOT EXISTS idx_urgent_requests_status ON urgent_requests(status);
