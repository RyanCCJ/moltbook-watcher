from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class PublishedPostRecord(Base):
    __tablename__ = "published_post_records"
    __table_args__ = (
        UniqueConstraint("threads_post_id", name="uq_threads_post_id"),
        UniqueConstraint("source_url", name="uq_source_url_published"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    candidate_post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidate_posts.id", ondelete="CASCADE"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    threads_post_id: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=UTC)
    )
    attribution_link: Mapped[str] = mapped_column(String(2048), nullable=False)


class PublishedPostRecordRepository:
    async def exists_for_source_url(self, session: AsyncSession, source_url: str) -> bool:
        statement = select(PublishedPostRecord.id).where(PublishedPostRecord.source_url == source_url)
        return (await session.scalar(statement)) is not None

    async def create(
        self,
        session: AsyncSession,
        *,
        candidate_post_id: str,
        source_url: str,
        threads_post_id: str,
        attribution_link: str,
    ) -> PublishedPostRecord:
        record = PublishedPostRecord(
            candidate_post_id=candidate_post_id,
            source_url=source_url,
            threads_post_id=threads_post_id,
            attribution_link=attribution_link,
        )
        session.add(record)
        await session.flush()
        return record
