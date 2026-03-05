from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.integrations.moltbook_api_client import MoltbookComment, MoltbookPost
from src.models.base import Base
from src.models.candidate_post import CandidatePost
from src.models.publish_job import PublishJobRepository
from src.models.published_post_record import PublishedPostRecord
from src.models.review_item import ReviewItemRepository
from src.services.publish_mode_service import PublishControlService
from src.services.review_payload_service import ReviewPayloadService
from src.workers.ingestion_worker import IngestionWorker
from src.workers.publish_worker import PublishWorker


class E2EMoltbookClient:
    async def list_posts(self, window: str, cursor: str | None = None, limit: int = 100, sort: str = "top"):
        _ = (window, cursor, limit, sort)
        return (
            [
                MoltbookPost(
                    source_url="https://moltbook.com/p/e2e-1",
                    source_post_id="e2e-1",
                    author_handle="e2e",
                    content_text="End-to-end publish candidate",
                    created_at=datetime.now(tz=UTC),
                    engagement_summary={"likes": 5},
                )
            ],
            None,
        )

    async def fetch_comments(self, post_id: str, limit: int = 5, sort: str = "top"):
        _ = (post_id, limit, sort)
        return [MoltbookComment(author_handle="e2e-comment", content_text="Interesting", upvotes=6)]


class E2EThreadsClient:
    def __init__(self) -> None:
        self.published_texts: list[str] = []

    async def publish_post(self, *, text: str, source_url: str) -> str:
        _ = source_url
        self.published_texts.append(text)
        return "threads-e2e-1"


class NoopNotificationService:
    async def notify_terminal_failure(self, session, publish_job, error_message: str) -> None:
        _ = (session, publish_job, error_message)


@pytest.mark.asyncio
async def test_candidate_to_publish_e2e_smoke() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    class _Scorer:
        def score_candidate(self, content_text: str, engagement_summary=None, top_comments=None):
            _ = (content_text, engagement_summary, top_comments)
            from src.services.scoring_service import ScoreResult

            return ScoreResult(
                novelty=4.0,
                depth=4.0,
                tension=4.0,
                reflective_impact=4.0,
                engagement=4.0,
                risk=1,
                content_score=4.0,
                final_score=3.8,
                score_version="e2e",
            )

    moltbook_client = E2EMoltbookClient()
    ingestion_worker = IngestionWorker(moltbook_client=moltbook_client, scoring_service=_Scorer())
    review_repo = ReviewItemRepository()
    publish_repo = PublishJobRepository()
    payload_builder = ReviewPayloadService(use_ollama=False)

    async with async_session() as session:
        metrics = await ingestion_worker.run_cycle(session, window="today")
        assert metrics.persisted_count == 1

        candidate_obj = (await session.scalars(select(CandidatePost))).first()
        assert candidate_obj is not None

        comments = await moltbook_client.fetch_comments(candidate_obj.source_post_id or "")
        payload = payload_builder.build_payload(
            raw_content=candidate_obj.raw_content,
            risk_score=1,
            top_comments=comments,
            final_score=3.8,
            source_url=candidate_obj.source_url,
        )
        review_item = await review_repo.create(
            session,
            candidate_post_id=candidate_obj.id,
            english_draft=payload.english_draft,
            chinese_translation_full=payload.chinese_translation_full,
            risk_tags=payload.risk_tags,
            top_comments_snapshot=payload.top_comments_snapshot,
            top_comments_translated=payload.top_comments_translated,
            threads_draft="Prepared draft for Threads\n\nhttps://moltbook.com/p/e2e-1",
        )
        await review_repo.decide(
            session,
            review_item_id=review_item.id,
            decision="approved",
            reviewed_by="e2e",
        )

        await publish_repo.create(
            session,
            candidate_post_id=candidate_obj.id,
            threads_account_key="account-1",
            scheduled_for=datetime.now(tz=UTC),
        )
        await session.commit()

    threads_client = E2EThreadsClient()
    publish_worker = PublishWorker(
        threads_client=threads_client,
        notification_service=NoopNotificationService(),
        control_service=PublishControlService(),
    )

    async with async_session() as session:
        await publish_worker.run_cycle(session)
        await session.commit()

        records = (await session.scalars(select(PublishedPostRecord))).all()

    assert len(records) == 1
    assert records[0].threads_post_id == "threads-e2e-1"
    assert threads_client.published_texts[0].startswith("Prepared draft for Threads")
