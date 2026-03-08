from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.integrations.moltbook_api_client import MoltbookComment, MoltbookPost
from src.models.base import Base
from src.models.candidate_post import CandidatePost
from src.models.published_post_record import PublishedPostRecord
from src.models.review_item import ReviewItem
from src.services.publish_mode_service import PublishControlService
from src.services.review_payload_service import ReviewPayload
from src.services.routing_service import RoutingService
from src.services.scoring_service import ScoreResult
from src.workers.ingestion_worker import IngestionWorker
from src.workers.publish_worker import PublishWorker
from src.workers.review_worker import ReviewWorker


class _MixedMoltbookClient:
    async def list_posts(self, time: str, cursor: str | None = None, limit: int = 100, sort: str = "top"):
        _ = (time, cursor, limit, sort)
        now = datetime.now(tz=UTC)
        return (
            [
                MoltbookPost(
                    source_url="https://example.com/low",
                    source_post_id="low",
                    author_handle="low",
                    content_text="low score candidate",
                    created_at=now,
                    engagement_summary={"likes": 1},
                ),
                MoltbookPost(
                    source_url="https://example.com/queue",
                    source_post_id="queue",
                    author_handle="queue",
                    content_text="review queue candidate",
                    created_at=now,
                    engagement_summary={"likes": 2},
                ),
                MoltbookPost(
                    source_url="https://example.com/auto",
                    source_post_id="auto",
                    author_handle="auto",
                    content_text="auto approve candidate",
                    created_at=now,
                    engagement_summary={"likes": 10},
                ),
            ],
            None,
        )

    async def fetch_comments(self, post_id: str, limit: int = 5, sort: str = "top"):
        _ = (limit, sort)
        return [MoltbookComment(author_handle="commenter", content_text=f"comment-{post_id}", upvotes=3)]


class _MixedScoringService:
    async def score_candidate(self, content_text: str, engagement_summary=None, top_comments=None) -> ScoreResult:
        _ = (engagement_summary, top_comments)
        scores = {
            "low score candidate": ScoreResult(
                novelty=3.0,
                depth=3.0,
                tension=3.0,
                reflective_impact=3.0,
                engagement=3.0,
                risk=1,
                content_score=3.0,
                final_score=3.2,
                score_version="integration",
            ),
            "review queue candidate": ScoreResult(
                novelty=4.0,
                depth=4.0,
                tension=4.0,
                reflective_impact=4.0,
                engagement=4.0,
                risk=2,
                content_score=4.0,
                final_score=3.7,
                score_version="integration",
            ),
            "auto approve candidate": ScoreResult(
                novelty=4.5,
                depth=4.5,
                tension=4.5,
                reflective_impact=4.5,
                engagement=4.5,
                risk=1,
                content_score=4.5,
                final_score=4.3,
                score_version="integration",
            ),
        }
        return scores[content_text]


class _StubPayloadService:
    async def build_payload(
        self,
        *,
        raw_content: str,
        risk_score: int,
        is_follow_up: bool = False,
        top_comments=None,
        final_score: float | None = None,
        source_url: str = "",
    ) -> ReviewPayload:
        _ = (risk_score, is_follow_up, top_comments, final_score)
        return ReviewPayload(
            english_draft=raw_content,
            chinese_translation_full="",
            risk_tags=["low-risk"],
            follow_up_rationale=None,
            top_comments_snapshot=[],
            top_comments_translated=[],
            threads_draft=f"Draft for {raw_content}\n\n{source_url}",
        )


class _StubThreadsClient:
    def __init__(self) -> None:
        self.published_texts: list[str] = []

    async def publish_post(self, *, text: str, source_url: str) -> str:
        _ = source_url
        self.published_texts.append(text)
        return "threads-post-1"


class _NoopNotificationService:
    async def notify_terminal_failure(self, session, publish_job, error_message: str) -> None:
        _ = (session, publish_job, error_message)


@pytest.mark.asyncio
async def test_full_ingestion_cycle_routes_archive_queue_and_auto_approve_candidates() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    control = PublishControlService(initial_mode="semi-auto")
    ingestion_worker = IngestionWorker(
        moltbook_client=_MixedMoltbookClient(),
        scoring_service=_MixedScoringService(),
        routing_service=RoutingService(fast_track_min_score=4.0),
        control_service=control,
        review_min_score=3.5,
    )
    review_worker = ReviewWorker(payload_service=_StubPayloadService())
    threads_client = _StubThreadsClient()
    publish_worker = PublishWorker(
        threads_client=threads_client,
        notification_service=_NoopNotificationService(),
        control_service=control,
    )

    async with async_session() as session:
        ingestion_metrics = await ingestion_worker.run_cycle(session, time="day", limit=20, sort="top")
        review_metrics = await review_worker.run_cycle(session)
        publish_metrics = await publish_worker.run_cycle(session)
        await session.commit()

        candidates = list((await session.scalars(select(CandidatePost).order_by(CandidatePost.source_post_id))).all())
        review_items = list((await session.scalars(select(ReviewItem).order_by(ReviewItem.candidate_post_id))).all())
        published_records = list((await session.scalars(select(PublishedPostRecord))).all())

    await engine.dispose()

    assert ingestion_metrics.persisted_count == 3
    assert ingestion_metrics.archived_count == 1
    assert ingestion_metrics.queued_count == 2
    assert ingestion_metrics.auto_approved_count == 1
    assert review_metrics.created_count == 2
    assert publish_metrics.published_count == 1

    by_post_id = {candidate.source_post_id: candidate for candidate in candidates}
    assert by_post_id["auto"].status == "published"
    assert by_post_id["low"].status == "archived"
    assert by_post_id["queue"].status == "queued"

    assert len(review_items) == 2
    decisions = {item.decision: item.reviewed_by for item in review_items}
    assert decisions["approved"] == "semi-auto"
    assert decisions["pending"] is None

    assert len(published_records) == 1
    assert threads_client.published_texts == ["Draft for auto approve candidate\n\nhttps://example.com/auto"]
