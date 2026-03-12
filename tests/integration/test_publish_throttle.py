"""
Tests for publish-throttle feature:
- 5.1 PublishedPostRecordRepository.count_since
- 5.2 PublishJobRepository.get_latest_scheduled_time
- 5.3 run_cycle skips when daily cap reached
- 5.4 _schedule_approved_candidates staggers by cooldown interval
- 5.5 _schedule_approved_candidates anchors to latest existing scheduled job
- 5.6 run_cycle processes at most 1 job per cycle
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models.base import Base
from src.models.candidate_post import CandidatePostRepository
from src.models.publish_job import PublishJob, PublishJobRepository
from src.models.published_post_record import PublishedPostRecord, PublishedPostRecordRepository
from src.models.review_item import ReviewItemRepository
from src.services.publish_mode_service import PublishControlService
from src.workers.publish_worker import PublishWorker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


async def _make_approved_candidate(session, candidate_repo, *, suffix: str, score: str = "fp"):
    candidate = await candidate_repo.create(
        session,
        source_url=f"https://example.com/{suffix}",
        source_time="hour",
        source_post_id=suffix,
        author_handle="test",
        raw_content=f"content-{suffix}",
        captured_at=datetime.now(tz=UTC),
        dedup_fingerprint=f"{score}-{suffix}",
    )
    await candidate_repo.transition_status(session, candidate, "scored")
    await candidate_repo.transition_status(session, candidate, "queued")
    await candidate_repo.transition_status(session, candidate, "reviewed")
    await candidate_repo.transition_status(session, candidate, "approved")
    return candidate


class FakeThreadsClient:
    def __init__(self, *, raise_error: bool = False) -> None:
        self.calls: list[str] = []
        self._raise = raise_error

    async def publish_post(self, *, text: str, source_url: str) -> str:
        self.calls.append(source_url)
        if self._raise:
            raise RuntimeError("forced error")
        return f"tid-{len(self.calls)}"


class FakeNotificationService:
    async def notify_terminal_failure(self, session, job, *, error_message: str) -> None:
        pass


def _make_worker(**kwargs) -> PublishWorker:
    return PublishWorker(
        threads_client=kwargs.pop("threads_client", FakeThreadsClient()),
        notification_service=FakeNotificationService(),
        control_service=PublishControlService(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 5.1 PublishedPostRecordRepository.count_since
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_count_since_returns_correct_count() -> None:
    engine = await _make_engine()
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    repo = PublishedPostRecordRepository()
    candidate_repo = CandidatePostRepository()

    now = datetime.now(tz=UTC)
    old_time = now - timedelta(hours=25)

    async with async_session() as session:
        # Create 3 candidates so we can link records to them
        candidates = []
        for i in range(5):
            c = await candidate_repo.create(
                session,
                source_url=f"https://example.com/c{i}",
                source_time="hour",
                source_post_id=f"c{i}",
                author_handle="test",
                raw_content=f"raw{i}",
                captured_at=now,
                dedup_fingerprint=f"fp{i}",
            )
            candidates.append(c)
        await session.commit()

    async with async_session() as session:
        # 3 recent records
        for i in range(3):
            record = PublishedPostRecord(
                candidate_post_id=candidates[i].id,
                source_url=f"https://example.com/c{i}",
                threads_post_id=f"t{i}",
                published_at=now - timedelta(hours=i),
                attribution_link=f"https://example.com/c{i}",
            )
            session.add(record)
        # 2 old records (older than 24h)
        for i in range(3, 5):
            record = PublishedPostRecord(
                candidate_post_id=candidates[i].id,
                source_url=f"https://example.com/c{i}",
                threads_post_id=f"t{i}",
                published_at=old_time,
                attribution_link=f"https://example.com/c{i}",
            )
            session.add(record)
        await session.commit()

    async with async_session() as session:
        since = now - timedelta(hours=24)
        count = await repo.count_since(session, since)

    assert count == 3


# ---------------------------------------------------------------------------
# 5.2 PublishJobRepository.get_latest_scheduled_time
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_latest_scheduled_time_returns_max_or_none() -> None:
    engine = await _make_engine()
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    job_repo = PublishJobRepository()
    candidate_repo = CandidatePostRepository()
    now = datetime.now(tz=UTC)

    # When no jobs exist ⇒ None
    async with async_session() as session:
        result = await job_repo.get_latest_scheduled_time(session)
    assert result is None

    # Create 3 scheduled jobs with different scheduled_for times
    t1 = now + timedelta(hours=1)
    t2 = now + timedelta(hours=5)
    t3 = now + timedelta(hours=3)
    async with async_session() as session:
        for i, t in enumerate([t1, t2, t3]):
            c = await candidate_repo.create(
                session,
                source_url=f"https://example.com/j{i}",
                source_time="hour",
                source_post_id=f"j{i}",
                author_handle="test",
                raw_content=f"raw{i}",
                captured_at=now,
                dedup_fingerprint=f"jfp{i}",
            )
            await job_repo.create(
                session,
                candidate_post_id=c.id,
                threads_account_key="acc",
                scheduled_for=t,
            )
        await session.commit()

    async with async_session() as session:
        latest = await job_repo.get_latest_scheduled_time(session)

    assert latest is not None
    # SQLite returns naive datetimes; compare without tz
    assert latest.replace(tzinfo=None) == t2.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# 5.3 run_cycle skips processing when daily cap is reached
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_cycle_skips_when_daily_cap_reached() -> None:
    engine = await _make_engine()
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    candidate_repo = CandidatePostRepository()
    PublishedPostRecordRepository()
    now = datetime.now(tz=UTC)

    # Create a published record to simulate daily cap reached (max=1)
    async with async_session() as session:
        c = await candidate_repo.create(
            session,
            source_url="https://example.com/already",
            source_time="hour",
            source_post_id="already",
            author_handle="test",
            raw_content="already published",
            captured_at=now,
            dedup_fingerprint="fp-already",
        )
        record = PublishedPostRecord(
            candidate_post_id=c.id,
            source_url="https://example.com/already",
            threads_post_id="t-already",
            published_at=now - timedelta(hours=1),
            attribution_link="https://example.com/already",
        )
        session.add(record)

        # Create an approved candidate that would normally be queued
        await _make_approved_candidate(session, candidate_repo, suffix="pending")
        await session.commit()

    threads_client = FakeThreadsClient()
    worker = _make_worker(threads_client=threads_client, max_publish_per_day=1, cooldown_minutes=0)

    async with async_session() as session:
        metrics = await worker.run_cycle(session)
        await session.commit()

    # Cap hit — nothing processed
    assert metrics.processed_count == 0
    assert metrics.published_count == 0
    assert len(threads_client.calls) == 0


# ---------------------------------------------------------------------------
# 5.4 _schedule_approved_candidates staggers by cooldown interval
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_schedule_approved_candidates_staggers_jobs() -> None:
    engine = await _make_engine()
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    candidate_repo = CandidatePostRepository()
    datetime.now(tz=UTC)

    async with async_session() as session:
        for i in range(3):
            await _make_approved_candidate(session, candidate_repo, suffix=f"stagger{i}")
        await session.commit()

    cooldown = 60  # 60-minute cooldown
    # Use max_publish_per_day=0 to disable daily cap
    worker = _make_worker(cooldown_minutes=cooldown, max_publish_per_day=0)

    async with async_session() as session:
        metrics = await worker.run_cycle(session)
        jobs = list((await session.scalars(select(PublishJob).order_by(PublishJob.created_at.asc()))).all())
        await session.commit()

    assert metrics.scheduled_count == 3
    assert len(jobs) == 3

    # Jobs should be staggered by cooldown minutes (allow minor clock drift)
    t0 = jobs[0].scheduled_for
    t1 = jobs[1].scheduled_for
    t2 = jobs[2].scheduled_for

    # Normalize to naive for arithmetic
    def naive(dt: datetime) -> datetime:
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    gap1 = (naive(t1) - naive(t0)).total_seconds() / 60
    gap2 = (naive(t2) - naive(t1)).total_seconds() / 60
    assert abs(gap1 - cooldown) < 2, f"expected ~{cooldown}min gap, got {gap1}"
    assert abs(gap2 - cooldown) < 2, f"expected ~{cooldown}min gap, got {gap2}"


# ---------------------------------------------------------------------------
# 5.5 _schedule_approved_candidates anchors to latest existing scheduled job
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_schedule_approved_candidates_anchors_to_latest_existing() -> None:
    engine = await _make_engine()
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    candidate_repo = CandidatePostRepository()
    job_repo = PublishJobRepository()
    now = datetime.now(tz=UTC)
    cooldown = 240  # 4 hours

    # Pre-existing scheduled job at now + 8h (already future)
    existing_scheduled_for = now + timedelta(hours=8)

    async with async_session() as session:
        c_existing = await candidate_repo.create(
            session,
            source_url="https://example.com/existing",
            source_time="hour",
            source_post_id="existing",
            author_handle="test",
            raw_content="existing",
            captured_at=now,
            dedup_fingerprint="fp-existing",
        )
        await job_repo.create(
            session,
            candidate_post_id=c_existing.id,
            threads_account_key="acc",
            scheduled_for=existing_scheduled_for,
        )
        # New approved candidate
        await _make_approved_candidate(session, candidate_repo, suffix="new-one")
        await session.commit()

    worker = _make_worker(cooldown_minutes=cooldown, max_publish_per_day=0)

    async with async_session() as session:
        await worker.run_cycle(session)
        jobs = list((await session.scalars(select(PublishJob).order_by(PublishJob.scheduled_for.asc()))).all())
        await session.commit()

    # 2 jobs: the pre-existing one + the new one
    assert len(jobs) == 2

    def naive(dt: datetime) -> datetime:
        return dt.replace(tzinfo=None) if dt else dt

    # The new job should be anchored at existing_scheduled_for + cooldown
    expected_new_time = existing_scheduled_for + timedelta(minutes=cooldown)
    new_job = jobs[1]  # sorted by scheduled_for ascending, so new job is second
    diff = abs((naive(new_job.scheduled_for) - naive(expected_new_time)).total_seconds())
    assert diff < 60, f"expected new job near {expected_new_time}, got {new_job.scheduled_for}"


# ---------------------------------------------------------------------------
# 5.6 run_cycle processes at most 1 job per cycle even when multiple are due
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_cycle_processes_at_most_one_job() -> None:
    engine = await _make_engine()
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    candidate_repo = CandidatePostRepository()
    job_repo = PublishJobRepository()
    review_repo = ReviewItemRepository()
    now = datetime.now(tz=UTC)

    async with async_session() as session:
        for i in range(3):
            c = await _make_approved_candidate(session, candidate_repo, suffix=f"multi{i}")
            await review_repo.create(
                session,
                candidate_post_id=c.id,
                english_draft="draft",
                chinese_translation_full="draft",
                risk_tags=[],
                threads_draft=f"threads draft {i}\n\nhttps://example.com/multi{i}",
            )
            await job_repo.create(
                session,
                candidate_post_id=c.id,
                threads_account_key="acc",
                scheduled_for=now - timedelta(minutes=1),  # all due
            )
        await session.commit()

    threads_client = FakeThreadsClient()
    # max_publish_per_day=0 means no cap applied; cooldown=0
    worker = _make_worker(threads_client=threads_client, max_publish_per_day=0, cooldown_minutes=0)

    async with async_session() as session:
        metrics = await worker.run_cycle(session)
        await session.commit()

    assert metrics.processed_count == 1
    assert metrics.published_count == 1
    assert len(threads_client.calls) == 1
