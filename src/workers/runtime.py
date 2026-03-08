from __future__ import annotations

from sqlalchemy import func, select

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
from src.models.review_item import ReviewItem
from src.services.logging_service import get_logger
from src.services.notification_service import NotificationService
from src.services.publish_mode_service import publish_control
from src.services.review_payload_service import ReviewPayloadService
from src.services.routing_service import RoutingService
from src.services.scoring_service import ScoringService
from src.services.telegram_service import TelegramService
from src.workers.ingestion_worker import IngestionWorker
from src.workers.publish_worker import PublishWorker
from src.workers.review_worker import ReviewWorker

logger = get_logger(__name__)


class IngestionCycleError(RuntimeError):
    pass


class ReviewCycleError(RuntimeError):
    pass


async def run_ingestion_once(
    time: str | None = None,
    limit: int | None = None,
    sort: str | None = None,
) -> dict[str, object]:
    settings = get_settings()
    resolved_time = time or settings.ingestion_time
    resolved_limit = limit if limit is not None else settings.ingestion_limit
    resolved_sort = sort or settings.ingestion_sort
    telegram_client: TelegramClient | None = None
    moltbook_client = MoltbookAPIClient(
        base_url=settings.moltbook_api_base_url,
        token=settings.moltbook_api_token,
    )
    scoring_service = ScoringService(
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
    )
    ingestion_worker = IngestionWorker(
        moltbook_client=moltbook_client,
        scoring_service=scoring_service,
        routing_service=RoutingService(fast_track_min_score=settings.auto_publish_min_score),
        review_min_score=settings.review_min_score,
    )
    review_payload_service = ReviewPayloadService(
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        translation_language=settings.translation_language,
        threads_language=settings.threads_language,
        threads_draft_min_score=settings.review_min_score,
    )
    review_worker = ReviewWorker(payload_service=review_payload_service)

    try:
        async with AsyncSessionLocal() as session:
            try:
                ingestion_metrics = await ingestion_worker.run_cycle(
                    session,
                    time=resolved_time,
                    limit=resolved_limit,
                    sort=resolved_sort,
                )
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

        pending_review_count = 0
        if settings.telegram_enabled and settings.telegram_chat_id.strip() and ingestion_metrics.persisted_count > 0:
            telegram_client = TelegramClient(settings.telegram_bot_token)
            telegram_service = TelegramService(telegram_client, settings.telegram_chat_id)
            async with AsyncSessionLocal() as session:
                pending_review_count = (
                    await session.scalar(
                        select(func.count())
                        .select_from(ReviewItem)
                        .where(ReviewItem.decision == ReviewDecision.PENDING.value)
                    )
                    or 0
                )
            try:
                auto_publish_label = "auto-approved" if publish_control.mode == "semi-auto" else "would qualify"
                auto_publish_count = (
                    ingestion_metrics.auto_approved_count
                    if publish_control.mode == "semi-auto"
                    else ingestion_metrics.fast_track_count
                )
                await telegram_client.send_message(
                    settings.telegram_chat_id,
                    telegram_service.format_ingestion_digest(
                        fetched_count=ingestion_metrics.fetched_count,
                        persisted_count=ingestion_metrics.persisted_count,
                        filtered_duplicate_count=ingestion_metrics.filtered_duplicate_count,
                        archived_count=ingestion_metrics.archived_count,
                        score_breakdown=ingestion_metrics.score_breakdown,
                        risk_breakdown=ingestion_metrics.risk_breakdown,
                        auto_publish_count=auto_publish_count,
                        auto_publish_label=auto_publish_label,
                        pending_total=pending_review_count,
                        review_min_score=settings.review_min_score,
                        auto_publish_min_score=settings.auto_publish_min_score,
                    ),
                )
            except Exception as error:
                logger.error("telegram_ingestion_digest_failed", error=str(error))
        return {
            "time": resolved_time,
            "sort": resolved_sort,
            "limit": resolved_limit,
            "fetched_count": ingestion_metrics.fetched_count,
            "persisted_count": ingestion_metrics.persisted_count,
            "scored_count": ingestion_metrics.scored_count,
            "queued_count": ingestion_metrics.queued_count,
            "archived_count": ingestion_metrics.archived_count,
            "auto_approved_count": ingestion_metrics.auto_approved_count,
            "auto_publish_ready_count": ingestion_metrics.fast_track_count,
            "filtered_duplicate_count": ingestion_metrics.filtered_duplicate_count,
            "score_breakdown": ingestion_metrics.score_breakdown,
            "risk_breakdown": ingestion_metrics.risk_breakdown,
            "pending_review_count": pending_review_count,
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
