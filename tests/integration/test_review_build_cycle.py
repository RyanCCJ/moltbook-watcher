from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.integrations.moltbook_api_client import MoltbookComment, MoltbookPost
from src.models.base import Base
from src.models.review_item import ReviewItem
from src.services.scoring_service import ScoreResult
from src.workers.ingestion_worker import IngestionWorker
from src.workers.review_worker import ReviewWorker


class ReviewBuildMoltbookClient:
    def __init__(self) -> None:
        self.fetch_comments_calls = 0

    async def list_posts(self, time: str, cursor: str | None = None, limit: int = 100, sort: str = "top"):
        _ = (time, cursor, limit, sort)
        return (
            [
                MoltbookPost(
                    source_url="https://www.moltbook.com/posts/review-build-1",
                    source_post_id="review-build-1",
                    author_handle="review-build",
                    content_text="Review queue build candidate",
                    created_at=datetime.now(tz=UTC),
                    engagement_summary={"likes": 5},
                )
            ],
            None,
        )

    async def fetch_comments(self, post_id: str, limit: int = 5, sort: str = "top"):
        _ = (post_id, limit, sort)
        self.fetch_comments_calls += 1
        return [MoltbookComment(author_handle="reviewer", content_text="Helpful context", upvotes=3)]


class ReviewBuildScorer:
    async def score_candidate(self, content_text: str, engagement_summary=None, top_comments=None):
        _ = (content_text, engagement_summary, top_comments)
        return ScoreResult(
            novelty=4.0,
            depth=4.0,
            tension=4.0,
            reflective_impact=4.0,
            engagement=4.0,
            risk=1,
            content_score=4.0,
            final_score=3.8,
            score_version="review-build-v1",
        )


@pytest.mark.asyncio
async def test_review_worker_builds_pending_review_items_from_queued_candidates() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    moltbook_client = ReviewBuildMoltbookClient()
    ingestion_worker = IngestionWorker(moltbook_client=moltbook_client, scoring_service=ReviewBuildScorer())
    from src.services.review_payload_service import ReviewPayloadService

    review_worker = ReviewWorker(payload_service=ReviewPayloadService(use_ollama=False))

    async with async_session() as session:
        await ingestion_worker.run_cycle(session, time="day")
        first = await review_worker.run_cycle(session)
        second = await review_worker.run_cycle(session)
        await session.commit()

        review_count = await session.scalar(select(func.count()).select_from(ReviewItem))
        review_item = (await session.scalars(select(ReviewItem))).first()

    assert first.created_count == 1
    assert second.created_count == 0
    assert review_count == 1
    assert review_item is not None
    assert review_item.top_comments_snapshot[0]["content_text"] == "Helpful context"
    assert review_item.top_comments_translated == []
    assert moltbook_client.fetch_comments_calls == 1
