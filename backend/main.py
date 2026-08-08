"""
SkillMe — FastAPI Backend
Main application entry point.

Run with:
    uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from db.database import db
from services.github_service import github_service
from services.scheduler_service import scheduler_service
from routes.admin import router as admin_router
from routes.students import router as students_router
from routes.webhooks import router as webhooks_router
from routes.certificates import router as certificates_router
from routes.payments import router as payments_router
from routes.auth import router as auth_router
from routes.referrals import router as referrals_router

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("skillme")

# Frontend root — one level up from backend/
FRONTEND_DIR = Path(__file__).parent.parent

# ──────────────────────────────────────────────
# App Lifecycle
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info("Starting SkillMe backend...")
    await db.connect()
    logger.info(f"Database connected: {settings.turso_db_url}")
    logger.info(f"GitHub org: {settings.github_org}")

    # Verify GitHub token on startup
    if settings.skillme_github_token:
        user = await github_service.verify_token()
        if user:
            logger.info(f"GitHub authenticated as: {user.get('login')}")
        else:
            logger.warning("GitHub token verification failed — check your SKILLME_GITHUB_TOKEN")
    else:
        logger.warning("No SKILLME_GITHUB_TOKEN configured — GitHub features will not work")

    # Start the task scheduler
    scheduler_service.start()

    yield

    # Shutdown
    logger.info("Shutting down SkillMe backend...")
    scheduler_service.shutdown()
    await github_service.close()
    await db.disconnect()
    logger.info("Cleanup complete.")


# ──────────────────────────────────────────────
# App Setup
# ──────────────────────────────────────────────

app = FastAPI(
    title="SkillMe API",
    description="Backend API for SkillMe — India's open-source internship platform. Manages batches, students, GitHub automation, and progress tracking.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow frontend requests
# In production: set ALLOWED_ORIGINS=https://your-app.vercel.app in Render env vars
_cors_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": f"Server Error: {str(exc)}"},
        headers={"Access-Control-Allow-Origin": "*"}
    )

# Mount routers
app.include_router(admin_router)
app.include_router(students_router)
app.include_router(webhooks_router)
app.include_router(certificates_router)
app.include_router(payments_router)
app.include_router(auth_router)
app.include_router(referrals_router)


# ──────────────────────────────────────────────
# Clean URL Routes (serve .html files without extension)
# ──────────────────────────────────────────────

_PAGES = {
    "admin":       "admin.html",
    "dashboard":   "dashboard.html",
    "apply":       "apply.html",
    "certificate": "certificate.html",
    "lor":         "lor.html",
    "contact":     "contact.html",
    "quiz":        "quiz.html",
    "privacy":     "privacy.html",
    "terms":       "terms.html",
    "refunds":     "refunds.html",
}

for _slug, _filename in _PAGES.items():
    _filepath = FRONTEND_DIR / _filename
    if _filepath.exists():
        # Create closure to capture the correct filepath
        def _make_handler(fp):
            async def _handler():
                return FileResponse(fp)
            _handler.__name__ = f"serve_{fp.stem}"
            return _handler
        app.get(f"/{_slug}", tags=["pages"], include_in_schema=False)(_make_handler(_filepath))

# Serve static assets (CSS, JS, images) from frontend root
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ──────────────────────────────────────────────
# Root Endpoint
# ──────────────────────────────────────────────

@app.get("/", tags=["health"])
async def root():
    """Health check endpoint."""
    return {
        "service": "SkillMe API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health():
    """Detailed health check."""
    github_ok = False
    if settings.skillme_github_token:
        user = await github_service.verify_token()
        github_ok = user is not None

    return {
        "status": "healthy",
        "database": "connected",
        "github": "connected" if github_ok else "disconnected",
        "org": settings.github_org,
    }
