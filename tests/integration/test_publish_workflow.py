from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models.base import Base
from src.models.candidate_post import CandidatePostRepository
from src.models.publish_job import PublishJob, PublishJobRepository
from src.models.published_post_record import PublishedPostRecord
from src.services.publish_mode_service import PublishControlService
from src.workers.publish_worker import PublishWorker


class FakeThreadsClient:
    def __init__(self, outcomes: list[str | Exception]) -> None:
        self._outcomes = outcomes

    async def publish_post(self, *, text: str, source_url: str) -> str:
        _ = (text, source_url)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeNotificationService:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def notify_terminal_failure(self, session, publish_job, error_message: str) -> None:
        _ = session
        self.events.append(f"{publish_job.id}:{error_message}")


@pytest.mark.asyncio
async def test_publish_worker_handles_retries_success_and_terminal_notification() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    candidate_repo = CandidatePostRepository()
    publish_repo = PublishJobRepository()

    async with async_session() as session:
        candidate_success = await candidate_repo.create(
            session,
            source_url="https://moltbook.com/p/success",
            source_window="today",
            source_post_id="success",
            author_handle="alice",
            raw_content="publish success",
            captured_at=datetime.now(tz=UTC),
            dedup_fingerprint="fp-success",
        )
        await candidate_repo.transition_status(session, candidate_success, "scored")
        await candidate_repo.transition_status(session, candidate_success, "queued")
        await candidate_repo.transition_status(session, candidate_success, "reviewed")
        await candidate_repo.transition_status(session, candidate_success, "approved")

        candidate_fail = await candidate_repo.create(
            session,
            source_url="https://moltbook.com/p/fail",
            source_window="today",
            source_post_id="fail",
            author_handle="bob",
            raw_content="publish fail",
            captured_at=datetime.now(tz=UTC),
            dedup_fingerprint="fp-fail",
        )
        await candidate_repo.transition_status(session, candidate_fail, "scored")
        await candidate_repo.transition_status(session, candidate_fail, "queued")
        await candidate_repo.transition_status(session, candidate_fail, "reviewed")
        await candidate_repo.transition_status(session, candidate_fail, "approved")

        await publish_repo.create(
            session,
            candidate_post_id=candidate_success.id,
            threads_account_key="account-1",
            scheduled_for=datetime.now(tz=UTC),
        )
        await publish_repo.create(
            session,
            candidate_post_id=candidate_fail.id,
            threads_account_key="account-1",
            scheduled_for=datetime.now(tz=UTC),
        )
        await session.commit()

    threads_client = FakeThreadsClient(
        outcomes=[Exception("transient-1"), Exception("transient-2"), "threads-success", Exception("fatal-1"), Exception("fatal-2"), Exception("fatal-3")]
    )
    notifications = FakeNotificationService()
    worker = PublishWorker(
        threads_client=threads_client,
        notification_service=notifications,
        control_service=PublishControlService(),
    )

    for _ in range(3):
        async with async_session() as session:
            await worker.run_cycle(session)
            await session.commit()

    async with async_session() as session:
        jobs = (await session.scalars(select(PublishJob).order_by(PublishJob.id))).all()
        records = (await session.scalars(select(PublishedPostRecord))).all()

    assert any(job.status == "published" for job in jobs)
    assert any(job.status == "failed_terminal" for job in jobs)
    assert len(records) == 1
    assert len(notifications.events) == 1
