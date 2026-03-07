from __future__ import annotations

from src.config.settings import get_settings
from src.integrations.moltbook_api_client import MoltbookAPIClient
from src.integrations.notification_client import (
    DisabledNotificationClient,
    TelegramNotificationClient,
)
from src.integrations.telegram_client import TelegramClient
from src.integrations.threads_client import ThreadsClient
from src.models.base import AsyncSessionLocal
from src.models.lifecycle import ReviewDecision
from src.services.logging_service import get_logger
from src.services.notification_service import NotificationService
from src.services.review_payload_service import ReviewPayloadService
from src.services.scoring_service import ScoringService
from src.services.telegram_reporting import load_review_item_payloads
from src.services.telegram_service import TelegramService
from src.workers.ingestion_worker import IngestionWorker
from src.workers.publish_worker import PublishWorker
from src.workers.review_worker import ReviewWorker

logger = get_logger(__name__)


class IngestionCycleError(RuntimeError):
    pass


class ReviewCycleError(RuntimeError):
    pass


async def run_ingestion_once(time: str = "hour", limit: int = 100, sort: str = "top") -> dict[str, int | str]:
    settings = get_settings()
    telegram_client: TelegramClient | None = None
    moltbook_client = MoltbookAPIClient(
        base_url=settings.moltbook_api_base_url,
        token=settings.moltbook_api_token,
    )
    scoring_service = ScoringService(
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
    )
    ingestion_worker = IngestionWorker(moltbook_client=moltbook_client, scoring_service=scoring_service)
    review_payload_service = ReviewPayloadService(
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        translation_language=settings.translation_language,
        threads_language=settings.threads_language,
    )
    review_worker = ReviewWorker(payload_service=review_payload_service)

    try:
        async with AsyncSessionLocal() as session:
            try:
                ingestion_metrics = await ingestion_worker.run_cycle(session, time=time, limit=limit, sort=sort)
                await session.commit()
            except Exception as error:
                await session.rollback()
                raise IngestionCycleError(str(error)) from error

        async with AsyncSessionLocal() as session:
            try:
                review_metrics = await review_worker.run_cycle(session)
                await session.commit()
            except Exception as error:
                await session.rollback()
                raise ReviewCycleError(str(error)) from error

        if settings.telegram_enabled and settings.telegram_chat_id.strip() and review_metrics.created_count > 0:
            telegram_client = TelegramClient(settings.telegram_bot_token)
            telegram_service = TelegramService(telegram_client, settings.telegram_chat_id)
            async with AsyncSessionLocal() as session:
                items = await load_review_item_payloads(
                    session,
                    status=ReviewDecision.PENDING.value,
                    limit=review_metrics.created_count,
                )
            try:
                await telegram_service.push_pending_items(items)
            except Exception as error:
                logger.error("telegram_pending_push_failed", error=str(error))
        return {
            "time": time,
            "sort": sort,
            "limit": limit,
            "fetched_count": ingestion_metrics.fetched_count,
            "persisted_count": ingestion_metrics.persisted_count,
            "filtered_duplicate_count": ingestion_metrics.filtered_duplicate_count,
            "review_items_created": review_metrics.created_count,
        }
    finally:
        await moltbook_client.close()
        if telegram_client is not None:
            await telegram_client.close()
        scoring_service.close()
        review_payload_service.close()


async def run_publish_once() -> dict[str, int]:
    settings = get_settings()
    telegram_client: TelegramClient | None = None
    threads_client = ThreadsClient(
        base_url=settings.threads_api_base_url,
        token=settings.threads_api_token,
        account_id=settings.threads_account_id,
    )
    if settings.telegram_enabled and settings.telegram_chat_id.strip():
        telegram_client = TelegramClient(settings.telegram_bot_token)
        notification_client = TelegramNotificationClient(telegram_client, settings.telegram_chat_id)
        default_recipient = settings.telegram_chat_id
    else:
        notification_client = DisabledNotificationClient()
        default_recipient = "telegram_disabled"
    notification_service = NotificationService(
        client=notification_client,
        default_recipient=default_recipient,
    )
    publish_worker = PublishWorker(
        threads_client=threads_client,
        notification_service=notification_service,
        threads_account_key=settings.threads_account_id,
    )

    try:
        async with AsyncSessionLocal() as session:
            try:
                metrics = await publish_worker.run_cycle(session)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return {
            "scheduled_count": metrics.scheduled_count,
            "processed_count": metrics.processed_count,
            "published_count": metrics.published_count,
            "retry_scheduled_count": metrics.retry_scheduled_count,
            "failed_terminal_count": metrics.failed_terminal_count,
            "cancelled_count": metrics.cancelled_count,
        }
    finally:
        await threads_client.close()
        if telegram_client is not None:
            await telegram_client.close()
