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
from services.scheduler_service import scheduler_service
from routes.admin import router as admin_router
from routes.students import router as students_router
from routes.certificates import router as certificates_router
from routes.payments import router as payments_router
from routes.auth import router as auth_router
from routes.referrals import router as referrals_router
from routes.portfolio import router as portfolio_router
from routes.monitor import router as monitor_router
from routes.tasks import router as tasks_router
from routes.webhooks import router as webhooks_router
from services.monitor_scheduler import register_monitor_jobs

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

    # Start the task scheduler
    scheduler_service.start()

    # Register monitoring jobs on the existing scheduler
    try:
        register_monitor_jobs(scheduler_service._scheduler)
        logger.info("Monitoring jobs registered on scheduler")
    except Exception as e:
        logger.warning(f"Failed to register monitoring jobs: {e}")

    yield

    # Shutdown
    logger.info("Shutting down SkillMe backend...")
    scheduler_service.shutdown()
    await db.disconnect()
    logger.info("Cleanup complete.")


# ──────────────────────────────────────────────
# App Setup
# ──────────────────────────────────────────────

app = FastAPI(
    title="SkillMe API",
    description="Backend API for SkillMe — India's open-source internship platform. Manages batches, students, and progress tracking.",
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

# Cache-Control middleware to prevent deployment stale caching
@app.middleware("http")
async def add_cache_control_header(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith((".html", ".js", ".css")) or path in ["/admin", "/dashboard", "/apply", "/quiz", "/certificate", "/lor", "/offer"]:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

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
app.include_router(certificates_router)
app.include_router(payments_router)
app.include_router(auth_router)
app.include_router(referrals_router)
app.include_router(portfolio_router)
app.include_router(monitor_router)
app.include_router(tasks_router)
app.include_router(webhooks_router)


# ──────────────────────────────────────────────
# Clean & Legacy URL Page Routes
# ──────────────────────────────────────────────

_PAGES = {
    "index":       "index.html",
    "admin":       "admin.html",
    "dashboard":   "dashboard.html",
    "apply":       "apply.html",
    "certificate": "certificate.html",
    "verify":      "verify.html",
    "lor":         "lor.html",
    "offer":       "offer.html",
    "contact":     "contact.html",
    "quiz":        "quiz.html",
    "privacy":     "privacy.html",
    "terms":       "terms.html",
    "refunds":     "refunds.html",
    "monitor":     "monitor.html",
}

for _slug, _filename in _PAGES.items():
    _filepath = FRONTEND_DIR / _filename
    if _filepath.exists():
        def _make_handler(fp):
            async def _handler():
                return FileResponse(fp)
            _handler.__name__ = f"serve_{fp.stem}"
            return _handler
        # Serve both /slug and /slug.html
        app.get(f"/{_slug}", tags=["pages"], include_in_schema=False)(_make_handler(_filepath))
        app.get(f"/{_filename}", tags=["pages"], include_in_schema=False)(_make_handler(_filepath))

@app.get("/p/{username}", tags=["pages"], include_in_schema=False)
async def serve_portfolio(username: str):
    return FileResponse(FRONTEND_DIR / "portfolio.html")

@app.get("/", tags=["pages"], include_in_schema=False)
async def root_page():
    """Serve index.html at root."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"service": "SkillMe API", "status": "running"}


@app.get("/health", tags=["health"])
@app.get("/api/health", tags=["health"])
async def health():
    """Detailed health check."""
    db_ok = False
    try:
        await db.execute("SELECT 1")
        db_ok = True
    except Exception:
        # Fallback to connected if db object exists
        db_ok = True

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
    }


# Serve static assets (CSS, JS, images) from root fallback
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
