# SkillMe — Online Internship Platform 🚀

SkillMe is an online internship program for students in India. Students apply, pass a short screening quiz, get an offer letter, complete weekly tasks in their chosen domain over 4 weeks, share their work as LinkedIn posts, and earn a verifiable certificate and LOR.

Live site: <https://www.skill-me-intern.in>

## How it works

1. **Apply** (`apply.html`) → **Quiz** (`quiz.html`) → shortlisted by email.
2. **Offer letter** and enrolment in a domain (web dev, Python, data science, QA, etc.).
3. **Weekly tasks** appear on the student dashboard. Each week the student posts about their work on LinkedIn and submits the post link.
4. **Admin review**: admins approve or reject each submission; students get an email either way.
5. **Completion**: certificate (optional paid, via Razorpay), letter of recommendation, and a public portfolio at `/p/<username>`.
6. Anyone can check a certificate on the **verify** page.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | HTML, CSS, vanilla JS — hosted on Vercel |
| Backend | FastAPI (Python 3.12) in Docker — hosted on Google Cloud Run |
| Database | [Turso](https://turso.tech) (libSQL) in production; a local SQLite file in development |
| Email | Brevo SMTP relay, with Brevo webhooks for delivery/open/bounce tracking |
| Payments | Razorpay (HMAC-verified) |
| Auth | Students: email OTP + JWT. Admins: `X-Admin-Key` header |

## Project structure

```
skill-me/
├── *.html                 # Pages: index, apply, quiz, dashboard, admin, tasks, verify,
│                          #   certificate, lor, offer, portfolio, contact, terms, privacy, refunds
├── config.js              # Picks API URL (localhost:8000 locally, Cloud Run in production)
├── docs.js                # Shared helpers: domain labels, PDF download
├── script.js, dashboard.js, admin.js, portfolio.js, dashboard-ui.js
├── style.css, dashboard.css
├── vercel.json            # Rewrites (/p/:github) and cache headers
├── archive/               # Old docs, migrations and tests kept for reference
├── tools/                 # LinkedIn autoposter and frontend check scripts (see tools/README.md)
├── .githooks/pre-commit   # JS syntax check (enable with: sh setup.sh)
└── backend/
    ├── main.py            # FastAPI app entry point
    ├── config.py          # Settings (pydantic-settings, read from env vars)
    ├── Dockerfile         # Cloud Run image (listens on 8080)
    ├── routes/            # admin, auth, certificates, payments, portfolio, students, tasks, webhooks
    ├── services/          # Business logic, email, scheduler, curriculum (curriculum.json + curriculum/)
    ├── db/                # schema.sql and the Turso/SQLite client
    ├── middleware/        # Admin and student auth
    ├── templates/emails/  # Jinja2 email templates
    ├── scripts/           # Manual maintenance/debug scripts (need TURSO_AUTH_TOKEN, see below)
    └── tests/             # pytest suite (see backend/tests/README.md)
```

## Local development

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in your values
uvicorn main:app --reload --port 8000
```
With `TURSO_DB_URL` unset the app uses a local SQLite file (`local.db`), so no cloud account is needed. API docs are at <http://localhost:8000/docs>.

### Frontend
```bash
# From the repo root
npx http-server -p 8080 --cors
```
Open <http://localhost:8080>. `config.js` automatically points at `localhost:8000`.

### Tests
```bash
cd backend
pytest
```
No production services are touched. See [backend/tests/README.md](backend/tests/README.md).

## Configuration

All backend settings are environment variables (see [backend/config.py](backend/config.py) and [backend/.env.production.example](backend/.env.production.example)):

| Variable | Purpose |
|----------|---------|
| `TURSO_DB_URL`, `TURSO_AUTH_TOKEN` | Production database. Leave unset for local SQLite |
| `ADMIN_API_KEY` | Admin console key — **set a strong value in production** |
| `JWT_SECRET_KEY` | Signs student sessions — **set a strong value in production** |
| `ALLOWED_ORIGINS` | Comma-separated frontend origins allowed by CORS |
| `FRONTEND_URL` | Used for links in emails |
| `SMTP_*`, `EMAIL_ENABLED` | Brevo SMTP relay |
| `BREVO_API_KEY`, `BREVO_WEBHOOK_SECRET` | Email engagement tracking |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `CERTIFICATE_PRICE_PAISE` | Payments |

Never commit real values. Manual scripts in `backend/scripts/` that talk to Turso read `TURSO_AUTH_TOKEN` from your shell environment:
```bash
export TURSO_AUTH_TOKEN="..."
python backend/scripts/debug_db.py
```

## Deployment

- **Frontend** → Vercel. Connect the repo with the root directory as `/`.
- JS/CSS are cached for a year, so after editing any `.js`/`.css` file run `python bump_versions.py` to stamp new content-hash `?v=` versions into the HTML (the pre-commit hook from `sh setup.sh` blocks commits that forget). `.vercelignore` keeps `backend/`, `archive/`, `tools/` and other non-site files out of the deploy.
- **Backend** → Google Cloud Run, built from `backend/Dockerfile`. Set the environment variables above on the service.
- After deploying the backend, make sure `PROD_API_URL` in [config.js](config.js) matches the Cloud Run URL, then redeploy the frontend.
- Health check: `GET /api/health`.

## License

MIT
