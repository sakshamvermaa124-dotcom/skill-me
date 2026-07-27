# SkillMe — Open-Source Internship Platform 🚀

India's first open-source internship platform. Students fix real GitHub issues, earn contributions, and get a verified certificate — all in 4 weeks.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | HTML, CSS, Vanilla JS (Vercel) |
| Backend | FastAPI + Python (Render) |
| Database | SQLite (persistent disk) |
| Email | Brevo SMTP |
| Payments | Razorpay |
| GitHub Automation | GitHub API + Webhooks |

## Project Structure

```
skill-me/
├── index.html          # Landing page
├── apply.html          # Application form
├── quiz.html           # Screening quiz
├── dashboard.html      # Student dashboard
├── admin.html          # Admin console
├── certificate.html    # Certificate viewer
├── config.js           # API URL configuration (auto-detects env)
├── style.css           # Shared styles
├── script.js           # Landing page scripts
├── dashboard.js        # Dashboard logic + Razorpay
├── admin.js            # Admin console logic
└── backend/
    ├── main.py         # FastAPI app entry point
    ├── config.py       # Settings (pydantic-settings)
    ├── requirements.txt
    ├── Procfile        # Render start command
    ├── render.yaml     # Render IaC config
    ├── routes/         # API route handlers
    ├── services/       # Business logic
    ├── db/             # SQLite schema + async client
    ├── middleware/     # Auth middleware
    └── templates/      # Jinja2 email templates
```

## Local Development

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in your values
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
# From root
npx http-server -p 8080 --cors
```

Open http://localhost:8080

## Deployment

- **Frontend** → [Vercel](https://vercel.com) — connect this repo, root dir = `/`
- **Backend** → [Render](https://render.com) — connect this repo, root dir = `/backend`

### Render Environment Variables

Copy from `backend/.env.production.example` and fill in real values in the Render dashboard.

Key variables to set:
- `DATABASE_PATH=/data/skillme.db`
- `ALLOWED_ORIGINS=https://your-app.vercel.app`
- `FRONTEND_URL=https://your-app.vercel.app`
- `SKILLME_GITHUB_TOKEN=ghp_...`
- `ADMIN_API_KEY=strong-random-key`

### After Deploying Backend

Update `config.js` in the frontend:
```js
const RENDER_URL = 'https://skillme-api.onrender.com';  // ← your actual URL
```

Then redeploy the frontend on Vercel.

## API Docs

Once deployed: `https://skillme-api.onrender.com/docs`

## License

MIT
