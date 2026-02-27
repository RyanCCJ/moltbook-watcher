from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.integrations.moltbook_api_client import MoltbookPost
from src.models.base import Base
from src.services.scoring_service import ScoreResult
from src.workers.ingestion_worker import IngestionWorker


class ThroughputClient:
    async def list_posts(self, window: str, cursor: str | None = None, limit: int = 100):
        _ = (window, cursor, limit)
        posts = [
            MoltbookPost(
                source_url=f"https://moltbook.com/p/{i}",
                source_post_id=str(i),
                author_handle="perf",
                content_text=f"Candidate {i} with unique content {i}",
                created_at=datetime.now(tz=UTC),
                engagement_summary={"likes": i % 10},
            )
            for i in range(500)
        ]
        return posts, None


class ThroughputScorer:
    def score_candidate(self, content_text: str, engagement_summary=None):
        _ = (content_text, engagement_summary)
        return ScoreResult(
            novelty=3.0,
            depth=3.0,
            tension=3.0,
            reflective_impact=3.0,
            engagement=3.0,
            risk=1,
            content_score=3.0,
            final_score=2.8,
            score_version="perf",
        )


@pytest.mark.asyncio
async def test_ingestion_handles_500_candidates_within_hourly_sla() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    worker = IngestionWorker(moltbook_client=ThroughputClient(), scoring_service=ThroughputScorer())

    async with async_session() as session:
        metrics = await worker.run_cycle(session, window="today")

    assert metrics.fetched_count == 500
    assert metrics.persisted_count == 500
    assert metrics.elapsed_ms < 60 * 60 * 1000
