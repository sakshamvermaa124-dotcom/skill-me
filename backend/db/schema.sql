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
