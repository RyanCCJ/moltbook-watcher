from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.ops_routes import router as ops_router
from src.api.publish_routes import router as publish_router
from src.api.review_routes import router as review_router
from src.api.telegram_routes import (
    build_telegram_webhook_secret,
)
from src.api.telegram_routes import (
    router as telegram_router,
)
from src.config.settings import get_settings
from src.integrations.telegram_client import TelegramClient
from src.models.base import check_db_health, get_session
from src.services.logging_service import configure_logging, get_logger
from src.services.queue_client import QueueClient
from src.services.telegram_service import TelegramService

logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Moltbook Threads Curation Bot", version="0.1.0")

    @app.on_event("startup")
    async def startup() -> None:
        app.state.settings = settings
        app.state.queue_client = QueueClient(settings.redis_url)
        await app.state.queue_client.connect()
        app.state.telegram_webhook_registered = False
        if settings.telegram_enabled:
            telegram_client = TelegramClient(settings.telegram_bot_token)
            app.state.telegram_client = telegram_client
            app.state.telegram_service = TelegramService(telegram_client, settings.telegram_chat_id)
            if settings.telegram_webhook_url.strip():
                await telegram_client.set_webhook(
                    settings.telegram_webhook_url,
                    build_telegram_webhook_secret(settings.telegram_bot_token),
                )
                app.state.telegram_webhook_registered = True
            else:
                logger.warning("telegram_webhook_registration_skipped", reason="missing_webhook_url")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        queue_client: QueueClient = app.state.queue_client
        await queue_client.close()
        telegram_client: TelegramClient | None = getattr(app.state, "telegram_client", None)
        if telegram_client is not None:
            await telegram_client.close()

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
    if settings.telegram_enabled:
        app.include_router(telegram_router)

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
