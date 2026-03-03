from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.integrations.moltbook_api_client import MoltbookPost
from src.models.base import Base
from src.models.review_item import ReviewItem
from src.services.scoring_service import ScoreResult
from src.workers.ingestion_worker import IngestionWorker
from src.workers.review_worker import ReviewWorker


class ReviewBuildMoltbookClient:
    async def list_posts(self, window: str, cursor: str | None = None, limit: int = 100, sort: str = "top"):
        _ = (window, cursor, limit, sort)
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


class ReviewBuildScorer:
    def score_candidate(self, content_text: str, engagement_summary=None):
        _ = (content_text, engagement_summary)
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

    ingestion_worker = IngestionWorker(moltbook_client=ReviewBuildMoltbookClient(), scoring_service=ReviewBuildScorer())
    review_worker = ReviewWorker()

    async with async_session() as session:
        await ingestion_worker.run_cycle(session, window="today")
        first = await review_worker.run_cycle(session)
        second = await review_worker.run_cycle(session)
        await session.commit()

        review_count = await session.scalar(select(func.count()).select_from(ReviewItem))

    assert first.created_count == 1
    assert second.created_count == 0
    assert review_count == 1
