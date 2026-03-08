from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.integrations.moltbook_api_client import MoltbookPost
from src.models.base import Base
from src.models.candidate_post import CandidatePost
from src.models.score_card import ScoreCard
from src.services.publish_mode_service import PublishControlService
from src.services.routing_service import RoutingService
from src.services.scoring_service import ScoreResult
from src.workers.ingestion_worker import IngestionWorker


class _SinglePostClient:
    def __init__(self, content_text: str) -> None:
        self._content_text = content_text

    async def list_posts(self, time: str, cursor: str | None = None, limit: int = 100, sort: str = "top"):
        _ = (time, cursor, limit, sort)
        return (
            [
                MoltbookPost(
                    source_url=f"https://example.com/{self._content_text.replace(' ', '-')}",
                    source_post_id="post-1",
                    author_handle="tester",
                    content_text=self._content_text,
                    created_at=datetime.now(tz=UTC),
                    engagement_summary={"likes": 5},
                )
            ],
            None,
        )

    async def fetch_comments(self, post_id: str, limit: int = 5, sort: str = "top"):
        _ = (post_id, limit, sort)
        return []


class _FixedScoringService:
    def __init__(self, score: ScoreResult) -> None:
        self._score = score

    async def score_candidate(self, content_text: str, engagement_summary=None, top_comments=None) -> ScoreResult:
        _ = (content_text, engagement_summary, top_comments)
        return self._score


async def _run_ingestion(score: ScoreResult, *, publish_mode: str = "manual-approval") -> tuple[object, CandidatePost, ScoreCard]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    worker = IngestionWorker(
        moltbook_client=_SinglePostClient("candidate body"),
        scoring_service=_FixedScoringService(score),
        routing_service=RoutingService(fast_track_min_score=4.0),
        control_service=PublishControlService(initial_mode=publish_mode),
        review_min_score=3.5,
    )

    async with async_session() as session:
        metrics = await worker.run_cycle(session, time="day")
        await session.commit()
        candidate = (await session.scalars(select(CandidatePost))).one()
        score_card = (await session.scalars(select(ScoreCard))).one()

    await engine.dispose()
    return metrics, candidate, score_card


@pytest.mark.asyncio
async def test_ingestion_worker_archives_low_score_candidates() -> None:
    metrics, candidate, score_card = await _run_ingestion(
        ScoreResult(
            novelty=3.0,
            depth=3.0,
            tension=3.0,
            reflective_impact=3.0,
            engagement=3.0,
            risk=1,
            content_score=3.0,
            final_score=3.2,
            score_version="test",
        )
    )

    assert candidate.status == "archived"
    assert score_card.route_decision == "review_queue"
    assert metrics.archived_count == 1
    assert metrics.queued_count == 0


@pytest.mark.asyncio
async def test_ingestion_worker_keeps_high_score_candidates_queued_in_manual_mode() -> None:
    metrics, candidate, score_card = await _run_ingestion(
        ScoreResult(
            novelty=4.0,
            depth=4.0,
            tension=4.0,
            reflective_impact=4.0,
            engagement=4.0,
            risk=2,
            content_score=4.0,
            final_score=3.8,
            score_version="test",
        )
    )

    assert candidate.status == "queued"
    assert score_card.route_decision == "review_queue"
    assert metrics.archived_count == 0
    assert metrics.queued_count == 1
    assert metrics.auto_approved_count == 0


@pytest.mark.asyncio
async def test_ingestion_worker_auto_approves_fast_track_candidates_in_semi_auto_mode() -> None:
    metrics, candidate, score_card = await _run_ingestion(
        ScoreResult(
            novelty=4.5,
            depth=4.5,
            tension=4.5,
            reflective_impact=4.5,
            engagement=4.5,
            risk=1,
            content_score=4.5,
            final_score=4.3,
            score_version="test",
        ),
        publish_mode="semi-auto",
    )

    assert candidate.status == "approved"
    assert score_card.route_decision == "fast_track"
    assert metrics.queued_count == 1
    assert metrics.auto_approved_count == 1
    assert metrics.fast_track_count == 1
