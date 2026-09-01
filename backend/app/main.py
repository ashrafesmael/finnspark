import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import config
from .database import Base, engine
from .routers import (
    auth, collaboration, courses, dashboards, disbursements, forms, investment, library, programs, references,
    reports, selection, tenancy,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler(Path(__file__).resolve().parents[1] / "logs" / "backend.log", mode="a")],
)
logger = logging.getLogger("finnspark")

app = FastAPI(title="finnspark — Accelerator & Investment Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    response = await call_next(request)
    # never cache API responses (fresh data for the SPA)
    if request.url.path.startswith(("/api/", "/auth/")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# routers mounted under /api and also under /{lang}/api (i18n path prefix, spec §8)
API_PREFIXES = ["/api", "/{lang}/api"]
for auth_prefix in ("/auth", "/api/auth"):
    app.include_router(auth.router, prefix=auth_prefix)
for router in (references.router, tenancy.router, forms.router, selection.router,
               programs.router, courses.router, library.router, investment.router,
               collaboration.router, dashboards.router, disbursements.router):
    for prefix in API_PREFIXES:
        app.include_router(router, prefix=prefix)

for prefix in API_PREFIXES:
    app.include_router(reports.router, prefix=prefix)

media_dir = config.MEDIA_DIR
os.makedirs(os.path.join(media_dir, "uploads"), exist_ok=True)
app.mount("/media", StaticFiles(directory=media_dir), name="media")


@app.get("/api/health/")
def health():
    return {"status": "ok", "app": config.APP_NAME}


@app.get("/api/config/")
def public_config():
    """Canonical origin for shareable links (falls back to window origin client-side)."""
    return {
        "app_name": config.APP_NAME,
        "public_base_url": config.PUBLIC_BASE_URL,
        "supported_languages": config.SUPPORTED_LANGUAGES,
    }


# ---- Serve the built React SPA (frontend/dist) with history-fallback -------------
# NOTE: registered LAST so it never shadows API routes.
DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (DIST_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{spa_path:path}", include_in_schema=False)
    async def spa(spa_path: str):
        """SPA history fallback: unknown non-API paths return index.html."""
        candidate = DIST_DIR / spa_path
        if spa_path and candidate.is_file() and DIST_DIR.resolve() in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html")
else:
    logger.warning("frontend/dist not found — build it with `npm run build`")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    _migrate(engine)
    logger.info("%s started — database %s", config.APP_NAME, config.DATABASE_URL)


def _migrate(engine):
    """Lightweight ad-hoc migrations for columns added after first release."""
    import sqlalchemy
    insp = sqlalchemy.inspect(engine)
    cols = {c["name"] for c in insp.get_columns("applicants")}
    with engine.begin() as conn:
        if "answer_labels" not in cols:
            conn.exec_driver_sql("ALTER TABLE applicants ADD COLUMN answer_labels JSON")
            logger.info("added applicants.answer_labels")
        if "invited_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE applicants ADD COLUMN invited_at DATETIME")
            logger.info("added applicants.invited_at")
