# SkillMe Internship Platform — Master Architecture & Project Documentation

**SkillMe** is India's first open-source, fully automated internship platform designed to scale the process of managing student developer cohorts, assigning them real-world engineering tasks via GitHub, verifying code submissions via CI/CD webhooks, processing certificate payments via Razorpay, and issuing verifiable on-chain certificates — all presented through a stunning, award-winning UI/UX interface.

This document serves as the **definitive source of truth** for any developer or AI/LLM working on the project. It details the complete architecture, database schema, automation pipelines, external integrations, design systems, and deployment configurations.

---

## 1. System Architecture & High-Level Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (Vercel)                              │
│  index.html | apply.html | quiz.html | dashboard.html | admin.html       │
│  Auto-detects API base via config.js (localhost vs Render production)    │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │ HTTPS (REST API & Webhooks)
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         BACKEND API (Render)                             │
│  FastAPI (Python 3.12.4) | uvicorn async server | Pydantic validation    │
└───────────┬────────────────────────┬─────────────────────────┬───────────┘
            │                        │                         │
            ▼                        ▼                         ▼
┌───────────────────────┐  ┌───────────────────┐  ┌────────────────────────┐
│  DATA & PERSISTENCE   │  │  EXTERNAL APIS    │  │  BACKGROUND SERVICES   │
│  SQLite (aiosqlite)   │  │  • GitHub API v3  │  │  • APScheduler (Weekly)│
│  Write-Ahead Log (WAL)│  │  • Brevo SMTP     │  │  • ReportLab PDF Engine │
│  Mounted on /data     │  │  • Razorpay Pay   │  │  • Async Email Workers │
└───────────────────────┘  └───────────────────┘  └────────────────────────┘
```

---

## 2. Comprehensive Directory & File Structure

```
skill-me/
├── index.html                   # Landing page (hero, features, domain cards, stats, CTA)
├── apply.html                   # Multi-step onboarding & application form with real-time validation
├── quiz.html                    # Interactive screening quiz assessing technical readiness
├── dashboard.html               # Student portal: progress tracking, GitHub timeline, payment & cert unlock
├── admin.html                   # Admin console: overview stats, student management, batch orchestration, email tools
├── certificate.html             # Verifiable web-based certificate viewer with gold ornamental styling
├── config.js                    # Global environment bridge (auto-assigns window.SKILLME_API & SKILLME_FRONTEND)
├── style.css                    # Shared UI design system (CSS variables, Aurora OLED dark mode, glassmorphism)
├── script.js                    # Landing page interactive logic and scroll animations
├── dashboard.js                 # Student portal client logic, chart rendering, and Razorpay checkout checkout flow
├── admin.js                     # Admin console state management, filtering, batch automation, and SMTP testing
├── vercel.json                  # Vercel static deployment config (cache-control rules, SPA routing rewrites)
├── README.md                    # Public GitHub documentation
└── backend/
    ├── main.py                  # FastAPI application entry point, CORS configuration, lifecycle manager
    ├── config.py                # Pydantic Settings model loading environment variables (.env / production)
    ├── requirements.txt         # Pinned Python dependencies (FastAPI, uvicorn, aiosqlite, razorpay, reportlab, etc.)
    ├── Procfile                 # Render start command (uvicorn main:app --host 0.0.0.0 --port $PORT)
    ├── render.yaml              # Render infrastructure-as-code configuration
    ├── .python-version          # Pinned to 3.12.4 to ensure binary wheel usage during cloud builds
    ├── cli.py                   # Click-powered terminal management tool for offline admin tasks
    ├── db/
    │   ├── database.py          # Async SQLite connection manager with WAL mode activation
    │   └── schema.sql           # Complete relational database DDL (students, batches, issues, payments, etc.)
    ├── middleware/
    │   └── auth.py              # API key verification for admin routes & HMAC verification for webhooks
    ├── routes/
    │   ├── admin.py             # Endpoints for stats, student review, batch creation, and task triggers
    │   ├── students.py          # Application submission, progress retrieval, and profile management
    │   ├── certificates.py      # On-the-fly PDF generation, verification, and administrative issuance
    │   ├── payments.py          # Razorpay order generation, HMAC SHA256 payment verification, status checks
    │   └── webhooks.py          # GitHub webhook receiver for automated PR and CI/CD tracking
    ├── services/
    │   ├── batch_service.py     # Batch creation, GitHub repository provisioning, and student enrollment
    │   ├── certificate_service.py # ReportLab PDF canvas drawing and SHA-256 certificate ID derivation
    │   ├── email_service.py     # Async SMTP relay wrapper (Brevo) with Jinja2 template rendering
    │   ├── github_service.py    # Async GitHub API client (repo creation, invitations, issue assignment)
    │   ├── scheduler_service.py # APScheduler cron engine for automated weekly task distribution
    │   └── task_service.py      # Task YAML frontmatter parser and markdown fetcher from central repo
    └── templates/
        └── emails/              # Jinja2 HTML email templates with inline responsive CSS
            ├── base.html        # Shared email wrapper with branding and footer
            ├── application_received.html # Fired on initial student application
            ├── shortlisted.html # Fired when admin shortlists candidate
            ├── offer_letter.html# Fired when student is enrolled into a cohort
            ├── weekly_tasks.html# Fired every Monday when scheduler assigns new issues
            └── certificate_ready.html # Fired after successful Razorpay certificate fee payment
```

---

## 3. Frontend & UI/UX Design System ("UI/UX Pro Max")

The frontend is engineered without heavy JavaScript frameworks (React/Vue) to guarantee **zero-bundle overhead**, instant page load speeds, and absolute DOM control, while achieving aesthetic standards rivaling top tier SaaS platforms.

### 3.1 Core Design Principles
- **Aurora OLED Dark Mode:** Deep black backgrounds (`#0a0a0c`) paired with vibrant, animated gradient floating orbs (purple `#8b5cf6`, cyan `#06b6d4`, emerald `#10b981`) that shift smoothly across the viewport.
- **Glassmorphism:** Multi-layered card structures utilizing `background: rgba(255, 255, 255, 0.03)`, `backdrop-filter: blur(16px)`, and subtle 1px borders (`rgba(255, 255, 255, 0.08)`), giving elements physical depth and separation.
- **Smooth Scrolling:** Integrated `@studio-freight/lenis` momentum-based scroll engine across every page for tactile, buttery-smooth navigation.
- **Micro-Interactions & Feedback:** Every interactive button, card, and input features hover scale transformations, glowing shadow enhancements, and immediate visual feedback.

### 3.2 Key Frontend Applications
1. **Landing Page (`index.html`)**: Includes dynamic counter animations, domain preview cards, and testimonials.
2. **Student Dashboard (`dashboard.html`)**:
   - **Progress Visualization:** Dynamic progress bars and live Chart.js graphs tracking weekly completion rates and PR merges.
   - **GitHub Activity Timeline:** A real-time chronological feed showing opened pull requests, CI/CD test results, and merged commits.
   - **Monetization & Reward Center:** Automatically displays a certificate unlock prompt once the student achieves 100% completion, integrating directly with Razorpay.
3. **Admin Console (`admin.html`)**:
   - **Secure Access:** Session-protected single-page dashboard authenticated via `X-Admin-Key`.
   - **Live Metric Counters:** Real-time summary statistics fetched via `/api/admin/stats`.
   - **Student Management Table:** Interactive data table allowing 1-click shortlisting, cohort enrollment (which triggers GitHub repository invitations), and status updates.
   - **Batch & Automation Hub:** Cohort creation tool and automated task scheduler toggles.
   - **Email Testing Sandbox:** Dedicated interface to ping the SMTP server, test individual templates, and verify deliverability.
4. **Certificate Viewer (`certificate.html`)**:
   - Web-based verification portal designed like a physical luxury diploma, featuring gold ornamental double borders, Cormorant Garamond italic typography, and cryptographic ID validation.

---

## 4. Backend Architecture & Relational Database

The backend is built on **FastAPI (Python 3.12.4)**, utilizing asynchronous I/O (`async/await`) across all database and network operations to ensure high concurrency without blocking the main event loop.

### 4.1 Database Schema (SQLite WAL Mode)
The database is initialized in **Write-Ahead Logging (WAL)** mode, allowing simultaneous reader and writer transactions without database locking errors.

```sql
-- Students table: Core user profiles and lifecycle status
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    college TEXT,
    year_of_study TEXT,
    github_handle TEXT NOT NULL,
    domain TEXT NOT NULL,
    motivation TEXT,
    status TEXT DEFAULT 'applied', -- applied, shortlisted, enrolled, completed, dropped
    payment_status TEXT DEFAULT 'unpaid', -- unpaid, paid
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Batches table: Domain-specific internship cohorts
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    batch_number INTEGER NOT NULL,
    github_repo TEXT, -- e.g., sakshamvermaa124-dotcom/skillme-web-dev-batch-1
    start_date DATE,
    end_date DATE,
    max_students INTEGER DEFAULT 50,
    status TEXT DEFAULT 'active',
    auto_assign INTEGER DEFAULT 1, -- 1 = enabled for Monday scheduler, 0 = disabled
    weeks_assigned TEXT DEFAULT '[]', -- JSON array of assigned weeks, e.g., [1, 2]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Enrollments table: Junction table mapping students to batches
CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER REFERENCES students(id),
    batch_id INTEGER REFERENCES batches(id),
    github_invited INTEGER DEFAULT 0, -- 0 = pending, 1 = invite sent
    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, batch_id)
);

-- Issues table: Maps curriculum tasks to real GitHub Issue IDs
CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER REFERENCES batches(id),
    week_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    github_issue_number INTEGER,
    github_issue_url TEXT,
    assigned_to TEXT, -- GitHub handle of the student
    status TEXT DEFAULT 'open', -- open, in_progress, completed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Submissions table: Tracks Pull Requests and CI/CD test results
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER REFERENCES issues(id),
    student_id INTEGER REFERENCES students(id),
    pr_url TEXT NOT NULL,
    pr_number INTEGER,
    status TEXT DEFAULT 'pending', -- pending, tests_passed, tests_failed, merged, closed
    feedback TEXT,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Progress table: Aggregated student performance metrics
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER REFERENCES students(id),
    batch_id INTEGER REFERENCES batches(id),
    issues_completed INTEGER DEFAULT 0,
    total_issues INTEGER DEFAULT 0,
    prs_merged INTEGER DEFAULT 0,
    current_week INTEGER DEFAULT 1,
    score INTEGER DEFAULT 0,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, batch_id)
);

-- Payments table: Razorpay transaction logs and HMAC verification verification records
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER REFERENCES students(id),
    batch_id INTEGER REFERENCES batches(id),
    razorpay_order_id TEXT UNIQUE NOT NULL,
    razorpay_payment_id TEXT,
    razorpay_signature TEXT,
    amount_paise INTEGER NOT NULL,
    status TEXT DEFAULT 'created', -- created, paid, failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP
);

-- Certificates table: Cryptographically derived certificate registry
CREATE TABLE IF NOT EXISTS certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cert_id TEXT UNIQUE NOT NULL, -- Format: SM-XXXX-XXXX-XXXX
    student_id INTEGER REFERENCES students(id),
    batch_id INTEGER REFERENCES batches(id),
    pdf_url TEXT,
    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. The GitHub Engine & Automated Task Curriculum

Instead of manually creating tasks, SkillMe operates an automated curriculum delivery pipeline backed by the GitHub REST API v3.

### 5.1 The Central Task Repository (`SkillMe-Intern-Tasks`)
We maintain a centralized public GitHub repository containing the exact curriculum for all internships. Tasks are stored as raw Markdown files structured by domain and week:
- `web-dev/week-1/task-1.md` through `task-3.md`
- `web-dev/week-2/task-1.md` through `task-3.md`
- `python/week-1/task-1.md` through `task-2.md`

Every markdown file utilizes **YAML Frontmatter** to define structured metadata:
```markdown
---
title: "Build Responsive Navigation Bar"
difficulty: "Beginner"
estimated_hours: 4
labels: ["frontend", "css", "responsive"]
---
# Task Description
Create a fully responsive navigation bar with a mobile hamburger toggle...
```

### 5.2 The Task Assignment Pipeline (`task_service.py` & `batch_service.py`)
When tasks are assigned (either manually by an admin or automatically by the weekly cron scheduler):
1. **Fetch & Parse:** `task_service.py` queries the GitHub Git Data API to list all markdown files in the folder corresponding to `domain/week-X`. It fetches the base64-encoded file content, strips and parses the YAML frontmatter, and extracts the raw markdown body.
2. **Provision Issues:** `batch_service.py` iterates through every student enrolled in the target batch. For each student, it sends an authenticated POST request to `https://api.github.com/repos/{batch_repo}/issues`, creating a live GitHub Issue assigned directly to the student's GitHub handle (`assignees: [student.github_handle]`).
3. **Database Sync:** The newly created GitHub Issue ID, URL, and assignment mapping are inserted into the `issues` table, instantly updating the student's dashboard progress counters.

### 5.3 Real-Time Progress Tracking via GitHub Webhooks (`webhooks.py`)
The platform requires zero manual grading. When a batch repository is created, a webhook pointing to `https://skill-me.onrender.com/api/webhooks/github` is automatically registered.

All incoming payloads are cryptographically validated against `WEBHOOK_SECRET` using HMAC SHA-256 (`X-Hub-Signature-256`).

| GitHub Event | Action Taken by Backend Engine |
| :--- | :--- |
| **`pull_request.opened`** | Identifies student via PR author username. Inserts/updates row in `submissions` table as `pending`. Sets corresponding issue status to `in_progress`. |
| **`check_suite.completed`** | Listens for automated CI/CD test results on student PRs.<br>• **If Tests Pass:** Updates submission status to `tests_passed` and posts an automated comment to the PR: *"✅ All tests passed! Great work."*<br>• **If Tests Fail:** Updates status to `tests_failed` and comments: *"❌ Some tests failed. Please review your CI build logs..."* |
| **`pull_request.closed` (merged)** | When a PR is merged into main: marks issue as `completed`, updates submission to `merged`, increments `issues_completed` and `prs_merged` in the `progress` table, adds points to student `score`, and checks if the student has reached 100% completion. |

---

## 6. Automated Weekly Scheduler (`scheduler_service.py`)

To eliminate manual administrative overhead, SkillMe runs an **APScheduler** background service running inside the FastAPI process.

- **Schedule:** Triggers every **Monday at 09:00 AM IST** (`cron`, day_of_week='mon', hour=9, minute=0).
- **Execution Logic:**
  1. Queries all batches where `status = 'active'` and `auto_assign = 1`.
  2. Calculates the current internship week based on the elapsed time since `start_date`:
     $$\text{Week Number} = \min\left(4, \max\left(1, \lfloor \frac{\text{Today} - \text{Start Date}}{7} \rfloor + 1\right)\right)$$
  3. Checks the `weeks_assigned` JSON array in the database. If the calculated week number is not yet present, it calls `assign_week_from_task_repo(batch_id, week_number)`.
  4. Automatically fires customizable email notifications (`weekly_tasks.html`) to all enrolled students with direct links to their new GitHub issues.
- **Admin Controls:** The Batches tab in the Admin Console provides per-cohort toggle switches to enable/disable auto-assign, as well as an emergency **"Trigger All Now"** button to execute the scheduler on demand.

---

## 7. Email Communication Relay (`email_service.py`)

The platform maintains automated engagement through a dedicated SMTP relay integration powered by **Brevo** (formerly Sendinblue), operating over Port 587 (STARTTLS).

### 7.1 Async Non-Blocking Architecture
To prevent email transmission latency from blocking FastAPI's async event loop, all email sending logic is executed in a background thread pool via `asyncio.to_thread(_send_sync)`.

### 7.2 Jinja2 Email Templates (`backend/templates/emails/`)
All emails are rendered using Jinja2 templates extending a common responsive `base.html` layout (dark themed, branded header, clean typography, responsive CTA button, and social footer).

| Template Name | Trigger Event | Key Variables Injected |
| :--- | :--- | :--- |
| **`application_received.html`** | Student submits application form | `student_name`, `domain`, `frontend_url` |
| **`shortlisted.html`** | Admin changes status to Shortlisted | `student_name`, `domain`, `frontend_url` |
| **`offer_letter.html`** | Admin enrolls student into a batch | `student_name`, `domain`, `batch_number`, `repo_url` |
| **`weekly_tasks.html`** | Monday scheduler assigns new curriculum | `student_name`, `domain`, `week_num`, `task_count`, `repo_url` |
| **`certificate_ready.html`** | Successful Razorpay fee verification | `student_name`, `domain`, `cert_id`, `download_url`, `verify_url` |

---

## 8. Payment Gateway Integration (Razorpay)

To unlock their official verified certificate upon achieving 100% course completion, students complete a secure checkout flow integrated with **Razorpay**.

### 8.1 The Payment Verification Lifecycle
```
Student Dashboard              FastAPI Backend                 Razorpay API
       │                              │                             │
       │── 1. Click "Unlock Cert" ───>│                             │
       │                              │── 2. POST /orders/create ──>│
       │                              │<── Returns Order ID ────────│
       │<── 3. Return Order Details ──│                             │
       │                              │                             │
       │── 4. Open Razorpay Modal ─────────────────────────────────>│
       │<── 5. Student Completes Payment ───────────────────────────│
       │                              │                             │
       │── 6. POST /api/payments/verify (order_id, payment_id, sig) │
       │                              │── 7. Verify HMAC SHA-256 sig│
       │                              │── 8. Update DB & Issue Cert │
       │<── 9. Return Success & Cert ID                             │
```

1. **Order Creation (`POST /api/payments/create-order`):** When a student clicks unlock, the backend verifies they have completed 100% of their issues, initializes an order with Razorpay for `24900 paise` (₹249.00 INR), logs the transaction in the `payments` table as `created`, and returns the `order_id` to the frontend.
2. **Client Checkout (`dashboard.js`):** The frontend invokes the native Razorpay checkout modal (`new Razorpay(options).open()`) pre-populated with the student's name, email, and order token.
3. **Cryptographic Verification (`POST /api/payments/verify`):** Upon payment completion, Razorpay returns `razorpay_order_id`, `razorpay_payment_id`, and `razorpay_signature`. The backend computes the expected HMAC SHA-256 signature:
   $$\text{Expected Signature} = \text{HMAC-SHA256}(\text{order\_id} + "|" + \text{payment\_id}, \text{RAZORPAY\_KEY\_SECRET})$$
   If the signatures match using `hmac.compare_digest()`, the payment status is marked as `paid`, the student's status is upgraded to `completed`, `payment_status` is marked `paid`, and `certificate_service.issue_certificate()` is triggered immediately.

---

## 9. Certificate Engine & ReportLab PDF Generation

SkillMe generates verifiable, high-resolution PDF certificates on the fly without requiring browser automation or headless Chrome dependencies.

### 9.1 Deterministic Cryptographic ID Derivation
Every certificate receives a tamper-proof ID in the format `SM-XXXX-XXXX-XXXX`, generated deterministically from the student and cohort identifiers:
```python
raw = f"cert-{student_id}-{batch_id}-skillme-2026"
hash_str = hashlib.sha256(raw.encode()).hexdigest().upper()
cert_id = f"SM-{hash_str[:4]}-{hash_str[4:8]}-{hash_str[8:12]}"
```

### 9.2 ReportLab PDF Engine (`certificate_service.py`)
When a user requests a PDF download (`GET /api/certificates/download/{student_id}/{batch_id}`):
- A ReportLab `Canvas` is initialized in memory over a standard **A4 Landscape** page (11.69 x 8.27 inches).
- **Background & Theme:** Draws an Aurora dark background replicating `#0a0a0c`, overlaid with radial glowing gradients (purple, cyan, gold).
- **Ornamental Frames:** Renders a luxury gold double-border (`#d4af37`) with intricate 4-corner geometric accent markers.
- **Typography Layout:** Centers the student's name in `Helvetica-Bold` at 32pt, underscored by a decorative purple gradient bar. Renders citation text, domain title, issuance date, verification URL, and official signature blocks.
- **Streaming Response:** Returns the binary stream directly with HTTP header `Content-Disposition: attachment; filename="SkillMe-Certificate-{student.name}.pdf"`.

---

## 10. Complete API Endpoint Reference

All endpoints are hosted under `https://skill-me.onrender.com`. Interactive Swagger UI documentation is available at `/docs`.

### 10.1 Health & System
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Basic service ping and version check | Public |
| `GET` | `/health` | Deep diagnostic check (database connection, GitHub API token validity) | Public |

### 10.2 Student Lifecycle (`routes/students.py`)
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/students/apply` | Submit onboarding application and initialize student record | Public |
| `GET` | `/api/students/progress/{email}` | Retrieve student profile, batch details, completion %, and GitHub timeline | Public |
| `GET` | `/api/students/` | List all registered students (supporting status filtering) | Admin (`X-Admin-Key`) |

### 10.3 Administrative & Batch Orchestration (`routes/admin.py`)
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/admin/stats` | Live metric aggregates (total students, active cohorts, issue counts) | Admin (`X-Admin-Key`) |
| `POST` | `/api/admin/students/{id}/shortlist` | Upgrade applicant status to shortlisted & send notification email | Admin (`X-Admin-Key`) |
| `POST` | `/api/admin/students/{id}/enroll` | Enroll student into batch, invite to GitHub repo, and fire offer email | Admin (`X-Admin-Key`) |
| `POST` | `/api/admin/students/{id}/drop` | Remove student from active participation | Admin (`X-Admin-Key`) |
| `POST` | `/api/admin/batches/create` | Provision new cohort & initialize corresponding GitHub repository | Admin (`X-Admin-Key`) |
| `GET` | `/api/admin/batches/` | List all cohorts with enrollment counts and scheduler states | Admin (`X-Admin-Key`) |
| `POST` | `/api/admin/batches/{id}/assign-from-repo` | Manually trigger task assignment from central GitHub repo for a specific week | Admin (`X-Admin-Key`) |
| `POST` | `/api/admin/batches/{id}/toggle-auto-assign` | Enable or disable Monday scheduler automation for a specific batch | Admin (`X-Admin-Key`) |
| `POST` | `/api/admin/scheduler/trigger-all` | Globally trigger automated task assignment across all eligible cohorts | Admin (`X-Admin-Key`) |
| `POST` | `/api/admin/email/test` | Dispatch test email to specified recipient to verify SMTP functionality | Admin (`X-Admin-Key`) |

### 10.4 Webhooks, Payments & Certificates (`routes/webhooks.py`, `payments.py`, `certificates.py`)
| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/webhooks/github` | Receive and process GitHub PR and CI/CD events (HMAC verified) | GitHub Webhook |
| `POST` | `/api/payments/create-order` | Generate Razorpay transaction token for certificate fee | Public |
| `POST` | `/api/payments/verify` | Verify Razorpay HMAC signature, unlock profile, and issue certificate | Public |
| `GET` | `/api/payments/status/{student_id}/{batch_id}` | Check current payment verification state | Public |
| `GET` | `/api/certificates/verify/{cert_id}` | Cryptographically validate certificate authenticity | Public |
| `GET` | `/api/certificates/download/{student_id}/{batch_id}` | Generate and download high-resolution PDF certificate | Public |

---

## 11. Production Deployment & Cloud Infrastructure

SkillMe operates a modern decoupled cloud deployment stack designed for infinite frontend horizontal scaling and zero-maintenance backend execution.

### 11.1 Frontend Deployment (Vercel)
- **Repository:** `https://github.com/sakshamvermaa124-dotcom/skill-me`
- **Root Directory:** `/`
- **Environment Bridge (`config.js`):** Dynamically checks `window.location.hostname`. When running on `localhost`, it routes API requests to `http://localhost:8000`. When deployed on Vercel, it routes traffic to `https://skill-me.onrender.com`.
- **Caching (`vercel.json`):** HTML and `config.js` are served with `Cache-Control: no-cache, no-store, must-revalidate` to ensure instant updates. Static CSS and JS assets are cached at the CDN edge for 24 hours.

### 11.2 Backend Deployment (Render Web Service)
- **Service Name:** `skillme-api` (Hosted at `https://skill-me.onrender.com`)
- **Runtime & Build:** Python 3.12.4 (Explicitly pinned via `.python-version` in the root and `backend/` directory to prevent Render from falling back to Python 3.14 which lacks pre-built binary wheels for Rust-dependent packages like `pydantic-core`).
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT` (Read from `Procfile` / `render.yaml`).
- **Database Persistence:** SQLite database stored at `data/skillme.db`.

### 11.3 Production Environment Variables (Render)
The following variables must be configured in the Render dashboard under **Environment**:

```env
# Server & Database
PORT=10000
HOST=0.0.0.0
DATABASE_PATH=data/skillme.db

# GitHub Automation
SKILLME_GITHUB_TOKEN=ghp_... (Personal Access Token with repo and workflow scopes)
GITHUB_ORG=sakshamvermaa124-dotcom

# Security & Authentication
ADMIN_API_KEY=skillme-admin-production-2026
WEBHOOK_SECRET=my_super_secret_webhook_key_123
ALLOWED_ORIGINS=https://skill-me.vercel.app,*
FRONTEND_URL=https://skill-me.vercel.app

# Brevo SMTP Email Relay
EMAIL_ENABLED=True
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=b350fa001@smtp-brevo.com
SMTP_PASSWORD=xsmtpsib-...
SMTP_FROM_NAME=SkillMe Team
SMTP_FROM_EMAIL=sakshamverma124@gmail.com

# Razorpay Payment Gateway
RAZORPAY_KEY_ID=rzp_live_... (or rzp_test_... for sandbox)
RAZORPAY_KEY_SECRET=...
CERTIFICATE_PRICE_PAISE=24900
```

---

## 12. Local Development Setup Guide

To spin up the complete full-stack environment on a local development machine:

### 12.1 Backend Setup
```bash
# 1. Navigate to backend directory
cd backend

# 2. Create and activate Python virtual environment
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment template and configure secrets
cp .env.example .env

# 5. Launch asynchronous development server with hot-reload
uvicorn main:app --reload --port 8000
```

### 12.2 Frontend Setup
```bash
# From the project root directory, launch a lightweight static web server
npx http-server -p 8080 --cors

# Access the application at:
# Landing Page: http://localhost:8080/index.html
# Student Portal: http://localhost:8080/dashboard.html
# Admin Console: http://localhost:8080/admin.html (Login with key defined in .env)
```

---

## 13. Summary of Core Engineering Highlights
1. **Zero-Manual Grading:** End-to-end webhook verification of GitHub pull requests and CI/CD test workflows automatically calculates student completion percentages and updates database scores.
2. **Decoupled Curriculum Delivery:** Separation of internship task definitions (stored in a standalone GitHub repo) from the application backend allows non-technical administrators to update course content via standard Markdown edits without deploying code changes.
3. **Resilient Background Automation:** Integration of `APScheduler` guarantees automated weekly task delivery and email broadcasting without relying on external cron triggers or manual admin intervention.
4. **Cryptographic Integrity:** Use of deterministic SHA-256 hashing for certificate verification and strict HMAC SHA-256 signature validation across both GitHub Webhooks and Razorpay payment callbacks ensures complete system security against tampering.
