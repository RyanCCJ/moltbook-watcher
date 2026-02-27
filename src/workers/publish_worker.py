from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.candidate_post import CandidatePost, CandidatePostRepository
from src.models.lifecycle import CandidateStatus
from src.models.publish_job import PublishJob, PublishJobRepository
from src.models.published_post_record import PublishedPostRecordRepository
from src.services.publish_mode_service import PublishControlService, publish_control
from src.services.publish_retry_policy import PublishRetryPolicy


@dataclass(slots=True)
class PublishCycleMetrics:
    scheduled_count: int
    processed_count: int
    published_count: int
    retry_scheduled_count: int
    failed_terminal_count: int
    cancelled_count: int


class PublishWorker:
    def __init__(
        self,
        *,
        threads_client,
        notification_service,
        retry_policy: PublishRetryPolicy | None = None,
        control_service: PublishControlService | None = None,
        threads_account_key: str = "default-account",
    ) -> None:
        self._threads_client = threads_client
        self._notification_service = notification_service
        self._retry_policy = retry_policy or PublishRetryPolicy()
        self._control_service = control_service or publish_control
        self._threads_account_key = threads_account_key
        self._jobs = PublishJobRepository()
        self._records = PublishedPostRecordRepository()
        self._candidates = CandidatePostRepository()

    async def run_cycle(self, session: AsyncSession) -> PublishCycleMetrics:
        metrics = PublishCycleMetrics(
            scheduled_count=0,
            processed_count=0,
            published_count=0,
            retry_scheduled_count=0,
            failed_terminal_count=0,
            cancelled_count=0,
        )
        if not self._control_service.can_publish_anything():
            return metrics

        now = datetime.now(tz=UTC)
        metrics.scheduled_count = await self._schedule_approved_candidates(session, now)
        jobs = await self._jobs.list_due(session, now)

        for job in jobs:
            outcome = await self._run_single_job(session, job)
            metrics.processed_count += 1
            if outcome == "published":
                metrics.published_count += 1
            elif outcome == "retry_scheduled":
                metrics.retry_scheduled_count += 1
            elif outcome == "failed_terminal":
                metrics.failed_terminal_count += 1
            elif outcome == "cancelled":
                metrics.cancelled_count += 1

        return metrics

    async def _schedule_approved_candidates(self, session: AsyncSession, now: datetime) -> int:
        existing_candidate_ids = set((await session.scalars(select(PublishJob.candidate_post_id))).all())

        statement = select(CandidatePost).where(CandidatePost.status == CandidateStatus.APPROVED.value)
        if existing_candidate_ids:
            statement = statement.where(CandidatePost.id.notin_(list(existing_candidate_ids)))

        approved_candidates = list((await session.scalars(statement)).all())
        for candidate in approved_candidates:
            await self._jobs.create(
                session,
                candidate_post_id=candidate.id,
                threads_account_key=self._threads_account_key,
                scheduled_for=now,
            )
            await self._candidates.transition_status(session, candidate, CandidateStatus.SCHEDULED)

        return len(approved_candidates)

    async def _run_single_job(self, session: AsyncSession, job: PublishJob) -> str:
        candidate = await session.get(CandidatePost, job.candidate_post_id)
        if candidate is None:
            job.status = "cancelled"
            job.last_error_message = "Candidate not found"
            session.add(job)
            await session.flush()
            return "cancelled"

        if await self._records.exists_for_source_url(session, candidate.source_url):
            job.status = "cancelled"
            job.last_error_message = "Duplicate publish blocked"
            session.add(job)
            await session.flush()
            return "cancelled"

        if candidate.status == CandidateStatus.APPROVED.value:
            await self._candidates.transition_status(session, candidate, "scheduled")

        job.status = "in_progress"
        job.attempt_count += 1
        job.updated_at = datetime.now(tz=UTC)
        session.add(job)
        await session.flush()

        try:
            post_id = await self._threads_client.publish_post(
                text=candidate.raw_content,
                source_url=candidate.source_url,
            )
        except Exception as error:
            job.last_error_code = "publish_error"
            job.last_error_message = str(error)
            job.updated_at = datetime.now(tz=UTC)

            if self._retry_policy.should_retry(attempt_count=job.attempt_count):
                job.status = "scheduled"
                delay = self._retry_policy.next_delay_seconds(attempt_count=job.attempt_count)
                job.scheduled_for = datetime.now(tz=UTC) + timedelta(seconds=delay)
                outcome = "retry_scheduled"
            else:
                job.status = "failed_terminal"
                await self._notification_service.notify_terminal_failure(
                    session,
                    job,
                    error_message=str(error),
                )
                outcome = "failed_terminal"

            session.add(job)
            await session.flush()
            return outcome

        await self._records.create(
            session,
            candidate_post_id=candidate.id,
            source_url=candidate.source_url,
            threads_post_id=post_id,
            attribution_link=candidate.source_url,
        )
        await self._candidates.transition_status(session, candidate, "published")

        job.status = "published"
        job.last_error_code = None
        job.last_error_message = None
        job.updated_at = datetime.now(tz=UTC)
        session.add(job)
        await session.flush()
        return "published"
