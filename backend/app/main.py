import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.errors import AIError
from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.errors import AppError
from app.core.middleware import MaxBodySizeMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
VERSION = "2.1.0"


def run_migrations() -> None:
    """`alembic upgrade head`. Schema changes go through migrations, never create_all()."""
    from alembic import command
    from alembic.config import Config
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


async def _scheduler_loop():
    """Lightweight in-process scheduler (used when no Celery beat is running)."""
    from app.services import followup_service
    interval = max(settings.FOLLOWUP_CHECK_INTERVAL_MINUTES, 1) * 60
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await followup_service.run_scheduler_tick(db)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Scheduler tick failed: %s", e)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.AUTO_MIGRATE and settings.APP_ENV != "test":
        await asyncio.to_thread(run_migrations)
        logger.info("Database migrated to head")
    task = None
    if settings.INPROCESS_SCHEDULER and settings.APP_ENV != "test":
        task = asyncio.create_task(_scheduler_loop())
    yield
    if task:
        task.cancel()
    await engine.dispose()


app = FastAPI(title="ColdCraft API", version=VERSION, lifespan=lifespan)

# Middleware runs outermost-last-added-first; CORS must be outermost so errors still carry CORS headers.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(MaxBodySizeMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "X-API-Token"])


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse({"detail": exc.detail, **exc.extra}, status_code=exc.status_code)


@app.exception_handler(AIError)
async def ai_error_handler(_: Request, exc: AIError):
    logger.error("AI error: %s", exc.detail)
    return JSONResponse({"detail": f"AI step failed: {exc.detail}", "retryable": True}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.include_router(api_router, prefix="/api/v1")
app.include_router(health.router)
