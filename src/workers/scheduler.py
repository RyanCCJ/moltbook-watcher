from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config.settings import get_settings
from src.services.logging_service import configure_logging, get_logger
from src.workers.runtime import run_ingestion_once, run_publish_once

logger = get_logger(__name__)


async def run_ingestion_cycle() -> None:
    logger.info("ingestion_cycle_triggered", ts=datetime.now(tz=UTC).isoformat())
    try:
        metrics = await run_ingestion_once(window="past_hour")
    except Exception as error:
        logger.exception("ingestion_cycle_failed", ts=datetime.now(tz=UTC).isoformat(), error=str(error))
        return
    logger.info("ingestion_cycle_finished", ts=datetime.now(tz=UTC).isoformat(), **metrics)


async def run_publish_cycle() -> None:
    logger.info("publish_cycle_triggered", ts=datetime.now(tz=UTC).isoformat())
    try:
        metrics = await run_publish_once()
    except Exception as error:
        logger.exception("publish_cycle_failed", ts=datetime.now(tz=UTC).isoformat(), error=str(error))
        return
    logger.info("publish_cycle_finished", ts=datetime.now(tz=UTC).isoformat(), **metrics)


def build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(run_ingestion_cycle, "interval", minutes=settings.ingestion_interval_minutes)
    scheduler.add_job(run_publish_cycle, "interval", minutes=settings.publish_poll_minutes)
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
