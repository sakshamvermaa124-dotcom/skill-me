
# SkillMe Internship Platform — Complete Project Documentation

SkillMe is an open-source, fully automated internship platform designed to scale the process of managing student developer batches, assigning them real-world tasks via GitHub, and tracking their progress through a stunning UI/UX interface.

This document serves as a comprehensive overview of the architecture, features, and implementations built throughout the project's development lifecycle.

---

## 1. Frontend & UI/UX Architecture

The frontend was designed with a heavy focus on modern aesthetic principles, prioritizing deep user engagement and a premium feel. We leveraged Vanilla HTML/CSS/JS without heavy frameworks for raw performance, while integrating high-end design libraries.

### Design Principles (UI/UX Pro Max)
- **Glassmorphism:** Widespread use of translucent panels (`backdrop-filter: blur()`) paired with subtle glowing borders to create a layered, modern depth.
- **Aurora OLED Dark Mode:** Deep black backgrounds contrasted with vibrant, moving gradient orbs (Aurora effects) to draw the eye without overwhelming the content.
- **Micro-interactions:** Hover states with scale transformations, glow enhancements, and smooth transitions on all interactive elements.
- **Typography:** Implementation of clean, sans-serif web fonts (e.g., Inter, Space Grotesk) to maintain readability.

### Core Pages
- **Landing Page (`index.html`)**: Features a high-converting hero section with dynamic floating cards, animated application steps, and smooth scrolling.
- **Application Flow (`apply.html`)**: A multi-step form utilizing local state to guide students through providing their details, GitHub username, and domain preference with real-time validation.
- **Student Dashboard (`dashboard.html`)**: The crown jewel of the frontend. A highly visual data center featuring:
  - Welcome animations for the student.
  - A responsive progress bar calculating total internship completion.
  - Interactive charts (via Chart.js) visualizing weekly issue completion and PR merges.
  - A chronological "Recent Activity" timeline for GitHub interactions.

### Libraries Used
- **Lenis (`@studio-freight/lenis`)**: Implemented across the platform to provide buttery smooth, momentum-based scrolling, eliminating the clunky default browser scroll behavior.
- **Chart.js**: Used in the dashboard to render responsive, styled progress charts.
- **Lucide Icons**: Consistent, clean SVG iconography used across navigation and data cards.

---

## 2. Backend Architecture (FastAPI & SQLite)

The backend is a robust, asynchronous Python application designed to act as the central brain orchestrating GitHub APIs, database states, and frontend requests.

### Core Technologies
- **FastAPI**: Chosen for its high performance, native async support, and automatic OpenAPI documentation.
- **SQLite (`aiosqlite`)**: Used in Write-Ahead Logging (WAL) mode to handle concurrent asynchronous reads/writes efficiently.
- **Pydantic**: Enforces strict data validation across all API endpoints.

### Database Schema
The relational database tracks the entire lifecycle of an internship:
- `students`: Personal details, GitHub handles, and application status.
- `batches`: Groupings of students by domain (e.g., Web-Dev) tied to specific GitHub template repositories.
- `enrollments`: Many-to-many junction table managing which students are in which batches and tracking their GitHub invite status.
- `issues`: The specific tasks assigned to students, mapped to real GitHub Issue IDs.
- `submissions` & `progress`: Tables tracking Pull Requests, merges, and aggregated weekly scores.

---

## 3. Administrative CLI Toolkit

To manage the platform, a powerful Command Line Interface was built using the Python `click` library. This allows administrators to manage the lifecycle of batches directly from the terminal.

### Key CLI Commands
- `python cli.py create-batch [domain] [batch_number]`: Automatically creates a new batch in the database and provisions a new GitHub repository based on predefined templates.
- `python cli.py list-batches` / `batch-status`: Provides rich terminal outputs (via `rich` library) detailing the status and enrollment of active batches.
- `python cli.py add-student --email [email] --batch-id [id]`: Enrolls a student, updates the database, and automatically fires an API call to GitHub to invite the student as a collaborator on the batch repository.

---

## 4. The Issue Assignment Engine (GitHub Automation)

The most advanced feature of the backend is the automated task orchestration engine. Instead of manually creating issues, the system pulls definitions from a central source of truth and pushes them to students.

### The Central Tasks Repository
We provisioned a `SkillMe-Intern-Tasks` repository on GitHub. This repository holds the actual curriculum for the internships. 
- Tasks are defined as standard Markdown files organized by domain and week (e.g., `web-dev/week-1/task-1.md`).
- Each file utilizes **YAML Frontmatter** to define metadata such as `title`, `difficulty`, and `labels`.

### The Automated Pipeline
When an admin runs `python cli.py assign-issues --batch-id X --week Y`, the backend:
1. **Fetches**: `task_service.py` hits the GitHub API to pull all Markdown files for the specified domain and week from the central task repository.
2. **Parses**: It decodes the base64 content, extracts the YAML frontmatter, and formats the Markdown body.
3. **Pushes**: `batch_service.py` loops through every active student in the batch and uses the GitHub API to create an Issue in the batch's specific repository, automatically assigning it to the student's GitHub username.
4. **Records**: The assignment is recorded in the local SQLite database, immediately updating the student's dashboard to reflect the new tasks (e.g., updating "Issues Done" to `0 / 2`).

---

## 5. Automated Progress Tracking (GitHub Webhooks)

The platform is designed to track student progress seamlessly in real-time, removing the need for manual grading or progress reporting. This is achieved via a **GitHub Webhooks Integration**.

### Webhook Event Handling
- When a batch is created, a webhook is registered on the batch's GitHub repository pointing to the backend's `/api/webhooks/github` endpoint.
- All webhook payloads are cryptographically verified using HMAC SHA-256 (`X-Hub-Signature-256`) to ensure they originate from GitHub.

### Tracked Events
1. **`pull_request.opened`**: 
   - When a student opens a PR against the batch repository, the backend identifies the student by their GitHub username.
   - It records the submission as `open` in the `submissions` table, and updates the task status to `in_progress`.
2. **`check_suite.completed`**:
   - The backend listens for CI/CD test results on the PRs.
   - If tests pass, it updates the submission to `tests_passed` and automatically comments on the PR: *"✅ All tests passed! Great work."*
   - If tests fail, it updates to `tests_failed` and leaves actionable feedback: *"❌ Some tests failed. Please check the CI logs..."*
3. **`pull_request.closed` (merged)**:
   - When a PR is successfully merged, the system marks the corresponding issue as `completed`.
   - The student's `progress` row is incremented (`issues_completed + 1`, `prs_merged + 1`), and their `score` is updated.
   - This score update is instantly reflected on the Student Dashboard.

---

## 6. Admin Dashboard (Web UI)

To replace the terminal CLI for day-to-day management, a premium web-based Admin Console was built at `admin.html`.

### Authentication
- A full-screen login overlay greets the admin on first visit
- The `dev-admin-key` is validated against the backend before granting access
- The key is stored in `sessionStorage` for seamless tab refreshes

### Overview Tab
- **Stats Cards**: Total Students, Active Batches, Pending Applications, and Issues Assigned — all fetched live from a single `GET /api/admin/stats` API endpoint
- **Recent Applications** panel shows the latest student submissions with a 1-click Shortlist action
- **Active Batches** panel shows enrollment progress bars for all active cohorts

### Students Tab
- Full searchable, filterable table of all students with real-time client-side filtering
- Status badges (`applied`, `shortlisted`, `enrolled`, `completed`, `dropped`) with color-coded indicators
- Context-sensitive action buttons per row: Shortlist, Enroll (opens batch selection modal), or Drop
- Enrolling a student via the UI automatically invites them to the batch's GitHub repository

### Batches Tab
- Visual batch cards with animated enrollment progress bars
- **Create Batch** modal: select domain, batch number, and max students
- **Assign Tasks** button per batch: opens a modal to select week number → calls `POST /api/admin/batches/{id}/assign-from-repo` which fetches real tasks from the central task repo

### Design (UI/UX Pro Max)
- **Sidebar Navigation**: Fixed left sidebar with branded header, section labels, and active state indicators
- **Aurora OLED Dark Mode**: Animated gradient orbs on a deep black canvas
- **Glassmorphism Panels**: `backdrop-filter: blur()` on all cards and modals with subtle glow borders
- **Toast Notification System**: Non-blocking, auto-dismissing success/error toasts
- **Micro-interactions**: Hover lifts, progress bar animations, and smooth page transitions

---

## 7. Automated Task Assignment & Expanded Task Library

### Automated Weekly Scheduler

Built an `APScheduler`-powered background service (`scheduler_service.py`) that runs inside FastAPI and automatically assigns the correct week's tasks to all active batches — no admin input required.

**How it works:**
- Every **Monday at 09:00 IST**, the scheduler wakes up
- For each `active` batch with `auto_assign = 1`, it calculates the current internship week from `start_date` (Week 1 = days 1–7, Week 2 = days 8–14, etc.)
- If that week hasn't been assigned yet, it calls `assign_week_from_task_repo()` to fetch tasks from GitHub and push issues to all enrolled students
- The week number is recorded in `weeks_assigned` (a JSON array) to prevent duplicate assignments

**Admin controls (via the Admin Console Batches tab):**
- **Toggle switch per batch**: Enable/disable auto-assign per cohort
- **"Run Now" button**: Immediately triggers auto-assign for that batch (useful for testing)
- **"Trigger All Now" button** on Overview: Runs the scheduler globally across all enrolled batches
- **Scheduler Status panel** on Overview: Shows live status (running/stopped), next scheduled run time, and which batches are enrolled

### Expanded Task Library (20 tasks across 2 domains)

The `SkillMe-Intern-Tasks` central repository was seeded with a full 4-week curriculum for two domains:

**Web Development (12 tasks, Weeks 1–4)**
- Week 1: Navigation Bar, Hero Section, Responsive Card Grid
- Week 2: JS DOM / FAQ Accordion, Fetch API / GitHub Widget, Contact Form Validation
- Week 3: Scroll Animations (Intersection Observer), Dark/Light Mode Toggle, Accessible Modal Component
- Week 4: Lighthouse Performance Audit, Portfolio Deployment, Peer Code Review

**Python (8 tasks, Weeks 1–4)**
- Week 1: CLI Todo App, Web Scraper with BeautifulSoup
- Week 2: GitHub Stats Analyzer with Caching, Data Analysis with Pandas
- Week 3: FastAPI REST API, Automated Email Report
- Week 4: Full Stack App + Cloud Deployment, Technical Blog Post

---

## 8. Certificate Generator

Students who complete all 4 weeks of their internship receive an official **Certificate of Completion**, automatically generated and verified on-chain with a unique ID.

### Certificate Design (`certificate.html`)
- **Aurora OLED dark canvas** with animated radial glow orbs (purple, blue, emerald)
- **Subtle dot-grid overlay** for a premium technical feel
- **Gold ornamental double-border** with 4-corner decorative marks
- **Typography**: Cormorant Garamond (name in 3.4rem italic serif), Space Grotesk (metadata)
- **Content**: Student name with purple underline, domain in sky-blue, batch info, cert ID in gold, date, and signature line
- **4-color gradient accent bar** at the bottom (purple → blue → emerald → gold)
- **"Download PDF"** and **"Print"** action buttons (hidden on print)
- **Verify Section** below the certificate: shows green ✅ if cert ID is genuine, warning if preview

### PDF Generation (`certificate_service.py`)
- **ReportLab** generates true PDF in-memory (no temp files, no browser needed)
- Deterministic certificate ID: `SM-XXXX-XXXX-XXXX` derived from `SHA-256(student_id + batch_id)`
- Same dark theme replicated in ReportLab: gradient background, purple/blue/gold/emerald palette, ornamental borders, corner marks, Helvetica Bold typography
- Returned as a streaming PDF `Response` via FastAPI (`Content-Disposition: attachment`)

### API Endpoints (`routes/certificates.py`)
| Method | Endpoint | Access | Description |
|--------|----------|--------|-------------|
| `GET` | `/api/certificates/verify/{cert_id}` | Public | Verify cert authenticity |
| `GET` | `/api/certificates/download/{student_id}/{batch_id}` | Public | Download PDF |
| `POST` | `/api/certificates/issue/{student_id}/{batch_id}` | Admin | Issue & record cert |
| `GET` | `/api/certificates/` | Admin | List all issued certs |

### Integration Points
- **Student Dashboard**: A gold `🏆 Certificate` banner appears when `progress = 100%` with "View Certificate" and "Download PDF" buttons. Below 100%, a progress-hint bar shows how many % remain.
- **Admin Dashboard**: Each enrolled/completed student row in the Students tab has a gold `🏅 Certificate` button — clicking issues the cert and opens the certificate.html page.
- **Database**: All issued certificates stored in the `certificates` table with `cert_id`, `student_id`, `batch_id`, `issued_at`.

---

## Summary of Achievements

Through a combination of high-end frontend design and complex backend orchestration, SkillMe operates as a zero-friction internship platform. Admins manage the entire platform from a sleek web console — approving applications, creating batches, enrolling students, and toggling automated task delivery with a single switch. The scheduler handles the rest, pushing the correct week's tasks to every student automatically every Monday. Students experience a visually stunning, highly responsive dashboard that mirrors their real-world GitHub contributions in real-time.
