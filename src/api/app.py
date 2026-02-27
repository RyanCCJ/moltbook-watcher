from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.ops_routes import router as ops_router
from src.api.publish_routes import router as publish_router
from src.api.review_routes import router as review_router
from src.config.settings import get_settings
from src.models.base import check_db_health, get_session
from src.services.logging_service import configure_logging
from src.services.queue_client import QueueClient


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Moltbook Threads Curation Bot", version="0.1.0")

    @app.on_event("startup")
    async def startup() -> None:
        app.state.settings = settings
        app.state.queue_client = QueueClient(settings.redis_url)
        await app.state.queue_client.connect()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        queue_client: QueueClient = app.state.queue_client
        await queue_client.close()

    @app.get("/health")
    async def health(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
        db_ok = False
        queue_ok = False
        errors: list[str] = []

        try:
            db_ok = await check_db_health(session)
        except Exception as error:  # pragma: no cover - defensive path
            errors.append(f"database: {error.__class__.__name__}: {error}")

        try:
            queue_ok = await app.state.queue_client.ping()
        except Exception as error:  # pragma: no cover - defensive path
            errors.append(f"queue: {error.__class__.__name__}: {error}")

        return {
            "status": "ok" if db_ok and queue_ok else "degraded",
            "database": db_ok,
            "queue": queue_ok,
            "environment": settings.app_env,
            "errors": errors,
            "database_target": _format_database_target(settings.database_url),
            "redis_target": _format_redis_target(settings.redis_url),
        }

    @app.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(review_router)
    app.include_router(publish_router)
    app.include_router(ops_router)

    return app


app = create_app()


def _format_database_target(database_url: str) -> str:
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/") or "-"
    host = parsed.hostname or "-"
    port = parsed.port or "-"
    return f"{host}:{port}/{db_name}"


def _format_redis_target(redis_url: str) -> str:
    parsed = urlparse(redis_url)
    host = parsed.hostname or "-"
    port = parsed.port or "-"
    db_index = parsed.path.lstrip("/") or "0"
    return f"{host}:{port}/{db_index}"
