from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    candidate_post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidate_posts.id", ondelete="CASCADE"), nullable=False
    )
    threads_account_key: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=UTC)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=UTC)
    )


class PublishJobRepository:
    async def create(
        self,
        session: AsyncSession,
        *,
        candidate_post_id: str,
        threads_account_key: str,
        scheduled_for: datetime,
        max_attempts: int = 3,
    ) -> PublishJob:
        job = PublishJob(
            candidate_post_id=candidate_post_id,
            threads_account_key=threads_account_key,
            scheduled_for=scheduled_for,
            status="scheduled",
            attempt_count=0,
            max_attempts=max_attempts,
        )
        session.add(job)
        await session.flush()
        return job

    async def list_due(self, session: AsyncSession, now: datetime) -> list[PublishJob]:
        statement = (
            select(PublishJob)
            .where(PublishJob.status == "scheduled")
            .where(PublishJob.scheduled_for <= now)
            .order_by(PublishJob.created_at.asc())
        )
        return list((await session.scalars(statement)).all())

    async def list(self, session: AsyncSession, status: str | None = None) -> list[PublishJob]:
        statement = select(PublishJob).order_by(PublishJob.created_at.desc())
        if status:
            statement = statement.where(PublishJob.status == status)
        return list((await session.scalars(statement)).all())

    async def get_latest_scheduled_time(self, session: AsyncSession) -> datetime | None:
        statement = select(func.max(PublishJob.scheduled_for)).where(PublishJob.status == "scheduled")
        return await session.scalar(statement)
