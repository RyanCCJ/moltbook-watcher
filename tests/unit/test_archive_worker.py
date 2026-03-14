from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models.base import Base
from src.models.candidate_post import CandidatePost, CandidatePostRepository
from src.models.review_item import ReviewItem, ReviewItemRepository
from src.models.score_card import ScoreCardRepository
from src.workers.archive_worker import ArchiveWorker


async def _build_session_factory() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return session_factory


async def _create_review_item(
    session,
    *,
    source_post_id: str,
    captured_at: datetime,
    final_score: float,
    reviewed_by: str | None = None,
) -> tuple[str, str]:
    candidate_repo = CandidatePostRepository()
    review_repo = ReviewItemRepository()
    score_repo = ScoreCardRepository()

    candidate = await candidate_repo.create(
        session,
        source_url=f"https://example.com/{source_post_id}",
        source_time="day",
        source_post_id=source_post_id,
        author_handle="tester",
        raw_content=f"Raw content for {source_post_id}",
        captured_at=captured_at,
        dedup_fingerprint=f"fp-{source_post_id}",
    )
    await candidate_repo.transition_status(session, candidate, "scored")
    await candidate_repo.transition_status(session, candidate, "queued")
    review_item = await review_repo.create(
        session,
        candidate_post_id=candidate.id,
        english_draft=f"Draft for {source_post_id}. Extra sentence.",
        chinese_translation_full="翻譯內容",
        risk_tags=["low"],
        threads_draft=f"Threads draft for {source_post_id}",
    )
    await score_repo.create(
        session,
        candidate_post_id=candidate.id,
        novelty_score=4.0,
        depth_score=4.0,
        tension_score=4.0,
        reflective_impact_score=4.0,
        engagement_score=4.0,
        risk_score=1,
        content_score=4.0,
        final_score=final_score,
        score_version="v1",
    )
    if reviewed_by is not None:
        await review_repo.decide(
            session,
            review_item_id=review_item.id,
            decision="archived",
            reviewed_by=reviewed_by,
        )
    await session.commit()
    return candidate.id, review_item.id


@pytest.mark.asyncio
async def test_archive_stale_review_items_archives_only_old_queued_pending_items() -> None:
    session_factory = await _build_session_factory()
    worker = ArchiveWorker()

    async with session_factory() as session:
        old_candidate_id, old_review_id = await _create_review_item(
            session,
            source_post_id="old-item",
            captured_at=datetime.now(tz=UTC) - timedelta(days=20),
            final_score=4.6,
        )
        fresh_candidate_id, fresh_review_id = await _create_review_item(
            session,
            source_post_id="fresh-item",
            captured_at=datetime.now(tz=UTC) - timedelta(days=3),
            final_score=4.2,
        )

        archived_count = await worker.archive_stale_review_items(session)

        old_candidate = await session.get(CandidatePost, old_candidate_id)
        old_review = await session.get(ReviewItem, old_review_id)
        fresh_candidate = await session.get(CandidatePost, fresh_candidate_id)
        fresh_review = await session.get(ReviewItem, fresh_review_id)

    assert archived_count == 1
    assert old_candidate is not None and old_candidate.status == "archived"
    assert old_review is not None and old_review.decision == "archived"
    assert old_review.reviewed_by == "archive-worker"
    assert fresh_candidate is not None and fresh_candidate.status == "queued"
    assert fresh_review is not None and fresh_review.decision == "pending"


@pytest.mark.asyncio
async def test_build_todays_high_score_recall_filters_to_today_archive_worker_items() -> None:
    session_factory = await _build_session_factory()
    worker = ArchiveWorker()

    async with session_factory() as session:
        _, included_review_id = await _create_review_item(
            session,
            source_post_id="included",
            captured_at=datetime.now(tz=UTC) - timedelta(days=30),
            final_score=4.9,
            reviewed_by="archive-worker",
        )
        _, yesterday_review_id = await _create_review_item(
            session,
            source_post_id="yesterday",
            captured_at=datetime.now(tz=UTC) - timedelta(days=30),
            final_score=4.8,
            reviewed_by="archive-worker",
        )
        _, manual_review_id = await _create_review_item(
            session,
            source_post_id="manual",
            captured_at=datetime.now(tz=UTC) - timedelta(days=30),
            final_score=5.0,
            reviewed_by="telegram",
        )
        _, low_score_review_id = await _create_review_item(
            session,
            source_post_id="low-score",
            captured_at=datetime.now(tz=UTC) - timedelta(days=30),
            final_score=3.5,
            reviewed_by="archive-worker",
        )

        yesterday_review = await session.get(ReviewItem, yesterday_review_id)
        manual_review = await session.get(ReviewItem, manual_review_id)
        low_score_review = await session.get(ReviewItem, low_score_review_id)
        assert yesterday_review is not None
        yesterday_review.reviewed_at = datetime.now(tz=UTC) - timedelta(days=1)
        await session.commit()

        items = await worker.build_todays_high_score_recall(session)

    assert [item["reviewItemId"] for item in items] == [included_review_id]
    assert all(item["finalScore"] >= 4.0 for item in items)
    assert manual_review is not None
    assert low_score_review is not None


@pytest.mark.asyncio
async def test_recall_item_handles_success_already_recalled_and_not_eligible() -> None:
    session_factory = await _build_session_factory()
    worker = ArchiveWorker()

    async with session_factory() as session:
        candidate_id, review_id = await _create_review_item(
            session,
            source_post_id="recall-success",
            captured_at=datetime.now(tz=UTC) - timedelta(days=30),
            final_score=4.7,
            reviewed_by="archive-worker",
        )
        _, manual_review_id = await _create_review_item(
            session,
            source_post_id="manual-archive",
            captured_at=datetime.now(tz=UTC) - timedelta(days=30),
            final_score=4.8,
            reviewed_by="telegram",
        )

        outcome = await worker.recall_item(session, review_id)
        candidate = await session.get(CandidatePost, candidate_id)
        review_item = await session.get(ReviewItem, review_id)
        second_outcome = await worker.recall_item(session, review_id)
        manual_outcome = await worker.recall_item(session, manual_review_id)

    assert outcome == "recalled"
    assert candidate is not None and candidate.status == "queued"
    assert review_item is not None and review_item.decision == "pending"
    assert review_item.reviewed_by is None
    assert review_item.reviewed_at is None
    assert second_outcome == "already_recalled"
    assert manual_outcome == "not_eligible"
