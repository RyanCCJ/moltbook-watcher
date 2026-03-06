from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.integrations.moltbook_api_client import MoltbookComment, MoltbookPost
from src.models.base import Base
from src.models.candidate_post import CandidatePost
from src.models.score_card import ScoreCard
from src.services.scoring_service import ScoreResult
from src.workers.ingestion_worker import IngestionWorker


class FakeMoltbookClient:
    async def list_posts(self, window: str, cursor: str | None = None, limit: int = 100, sort: str = "top"):
        _ = (window, cursor, limit, sort)
        return (
            [
                MoltbookPost(
                    source_url="https://moltbook.com/p/1",
                    source_post_id="1",
                    author_handle="alice",
                    content_text="AI needs better review workflow",
                    created_at=datetime.now(tz=UTC),
                    engagement_summary={"likes": 2},
                ),
                MoltbookPost(
                    source_url="https://moltbook.com/p/2",
                    source_post_id="2",
                    author_handle="bob",
                    content_text="AI needs better review workflows",
                    created_at=datetime.now(tz=UTC),
                    engagement_summary={"likes": 1},
                ),
                MoltbookPost(
                    source_url="https://moltbook.com/p/3",
                    source_post_id="3",
                    author_handle="carol",
                    content_text="Shipping review queues should preserve cached comments",
                    created_at=datetime.now(tz=UTC),
                    engagement_summary={"likes": 7},
                ),
                MoltbookPost(
                    source_url="https://moltbook.com/p/4",
                    source_post_id=None,
                    author_handle="dora",
                    content_text="Missing source id should skip comments fetch",
                    created_at=datetime.now(tz=UTC),
                    engagement_summary={"likes": 4},
                ),
            ],
            None,
        )

    async def fetch_comments(self, post_id: str, limit: int = 5, sort: str = "top"):
        _ = (limit, sort)
        if post_id == "3":
            return []
        return [MoltbookComment(author_handle="commenter", content_text=f"Comment for {post_id}", upvotes=2)]


class FakeScoringService:
    async def score_candidate(
        self,
        content_text: str,
        engagement_summary: dict | None = None,
        top_comments: list[MoltbookComment] | None = None,
    ) -> ScoreResult:
        _ = (content_text, engagement_summary, top_comments)
        return ScoreResult(
            novelty=3.5,
            depth=3.5,
            tension=3.5,
            reflective_impact=3.5,
            engagement=3.5,
            risk=1,
            content_score=3.5,
            final_score=3.3,
            score_version="test-v1",
        )


@pytest.mark.asyncio
async def test_ingestion_cycle_filters_duplicates_and_persists_scores() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    worker = IngestionWorker(moltbook_client=FakeMoltbookClient(), scoring_service=FakeScoringService())

    async with async_session() as session:
        metrics = await worker.run_cycle(session, window="today")
        await session.commit()

        candidates = (await session.scalars(select(CandidatePost))).all()
        scores = (await session.scalars(select(ScoreCard))).all()

    assert metrics.fetched_count == 4
    assert metrics.persisted_count == 3
    assert metrics.filtered_duplicate_count == 1
    assert len(candidates) == 3
    assert len(scores) == 3
    assert all(candidate.status == "queued" for candidate in candidates)

    by_source_post_id = {candidate.source_post_id: candidate for candidate in candidates}
    assert by_source_post_id["1"].top_comments_snapshot == [
        {"author_handle": "commenter", "content_text": "Comment for 1", "upvotes": 2}
    ]
    assert by_source_post_id["3"].top_comments_snapshot == []
    assert by_source_post_id[None].top_comments_snapshot == []
