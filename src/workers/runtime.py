from __future__ import annotations

from src.config.settings import get_settings
from src.integrations.moltbook_api_client import MoltbookAPIClient
from src.integrations.notification_client import SMTPNotificationClient
from src.integrations.threads_client import ThreadsClient
from src.models.base import AsyncSessionLocal
from src.services.notification_service import NotificationService
from src.services.review_payload_service import ReviewPayloadService
from src.services.scoring_service import ScoringService
from src.workers.ingestion_worker import IngestionWorker
from src.workers.publish_worker import PublishWorker
from src.workers.review_worker import ReviewWorker


async def run_ingestion_once(window: str = "past_hour", limit: int = 100) -> dict[str, int]:
    settings = get_settings()
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
    )
    review_worker = ReviewWorker(payload_service=review_payload_service)

    try:
        async with AsyncSessionLocal() as session:
            try:
                ingestion_metrics = await ingestion_worker.run_cycle(session, window=window, limit=limit)
                review_metrics = await review_worker.run_cycle(session)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return {
            "fetched_count": ingestion_metrics.fetched_count,
            "persisted_count": ingestion_metrics.persisted_count,
            "filtered_duplicate_count": ingestion_metrics.filtered_duplicate_count,
            "review_items_created": review_metrics.created_count,
        }
    finally:
        await moltbook_client.close()
        scoring_service.close()
        review_payload_service.close()


async def run_publish_once() -> dict[str, int]:
    settings = get_settings()
    threads_client = ThreadsClient(
        base_url=settings.threads_api_base_url,
        token=settings.threads_api_token,
        account_id=settings.threads_account_id,
    )
    notification_service = NotificationService(
        client=SMTPNotificationClient(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            sender=settings.smtp_from,
            recipient=settings.smtp_to,
        ),
        default_recipient=settings.smtp_to,
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
