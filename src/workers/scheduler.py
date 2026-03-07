from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config.settings import get_settings
from src.integrations.telegram_client import TelegramClient
from src.models.base import AsyncSessionLocal
from src.services.logging_service import configure_logging, get_logger
from src.services.telegram_reporting import build_stats_payload
from src.services.telegram_service import TelegramService
from src.workers.runtime import (
    IngestionCycleError,
    ReviewCycleError,
    run_ingestion_once,
    run_publish_once,
)

logger = get_logger(__name__)


async def run_ingestion_cycle() -> None:
    logger.info("ingestion_cycle_triggered", ts=datetime.now(tz=UTC).isoformat())
    try:
        metrics = await run_ingestion_once(time="hour")
    except IngestionCycleError as error:
        logger.error("ingestion_phase_failed", ts=datetime.now(tz=UTC).isoformat(), error=str(error))
        return
    except ReviewCycleError as error:
        logger.error("review_phase_failed", ts=datetime.now(tz=UTC).isoformat(), error=str(error))
        return
    except Exception as error:
        logger.error("ingestion_cycle_failed", ts=datetime.now(tz=UTC).isoformat(), error=str(error))
        return
    logger.info("ingestion_cycle_finished", ts=datetime.now(tz=UTC).isoformat(), **metrics)


async def run_publish_cycle() -> None:
    logger.info("publish_cycle_triggered", ts=datetime.now(tz=UTC).isoformat())
    try:
        metrics = await run_publish_once()
    except Exception as error:
        logger.error("publish_cycle_failed", ts=datetime.now(tz=UTC).isoformat(), error=str(error))
        return
    logger.info("publish_cycle_finished", ts=datetime.now(tz=UTC).isoformat(), **metrics)


async def run_daily_summary_cycle() -> None:
    settings = get_settings()
    if not settings.telegram_enabled or not settings.telegram_chat_id.strip():
        return

    telegram_client = TelegramClient(settings.telegram_bot_token)
    telegram_service = TelegramService(telegram_client, settings.telegram_chat_id)
    try:
        async with AsyncSessionLocal() as session:
            stats = await build_stats_payload(session)
        await telegram_client.send_message(
            settings.telegram_chat_id,
            telegram_service.format_stats_message(stats),
        )
    except Exception as error:
        logger.error("telegram_daily_summary_failed", ts=datetime.now(tz=UTC).isoformat(), error=str(error))
    finally:
        await telegram_client.close()


def build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(run_ingestion_cycle, "interval", minutes=settings.ingestion_interval_minutes)
    scheduler.add_job(run_publish_cycle, "interval", minutes=settings.publish_poll_minutes)
    if settings.telegram_enabled and settings.telegram_chat_id.strip():
        scheduler.add_job(
            run_daily_summary_cycle,
            "cron",
            hour=settings.telegram_daily_summary_hour,
            timezone=settings.telegram_daily_summary_timezone,
        )
    return scheduler


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("scheduler_started", ingestion_minutes=settings.ingestion_interval_minutes)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
