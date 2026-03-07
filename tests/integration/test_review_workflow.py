from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models.base import Base
from src.models.candidate_post import CandidatePostRepository
from src.models.review_item import ReviewItemRepository


@pytest.mark.asyncio
async def test_review_decision_lifecycle_transitions() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    candidate_repo = CandidatePostRepository()
    review_repo = ReviewItemRepository()

    async with async_session() as session:
        candidate = await candidate_repo.create(
            session,
            source_url="https://moltbook.com/p/20",
            source_time="day",
            source_post_id="20",
            author_handle="alice",
            raw_content="Review me",
            captured_at=datetime.now(tz=UTC),
            dedup_fingerprint="hash",
        )
        await candidate_repo.transition_status(session, candidate, target_status="scored")
        await candidate_repo.transition_status(session, candidate, target_status="queued")

        review = await review_repo.create(
            session,
            candidate_post_id=candidate.id,
            english_draft="Draft",
            chinese_translation_full="Draft translation",
            risk_tags=["low"],
        )

        decided = await review_repo.decide(
            session,
            review_item_id=review.id,
            decision="approved",
            reviewed_by="operator",
        )
        await session.commit()

    assert decided.decision == "approved"
    assert decided.reviewed_by == "operator"
    assert decided.reviewed_at is not None
