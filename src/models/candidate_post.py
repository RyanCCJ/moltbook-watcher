from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.models.lifecycle import CandidateStatus, assert_candidate_transition


class CandidatePost(Base):
    __tablename__ = "candidate_posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    source_time: Mapped[str] = mapped_column(String(32), nullable=False)
    source_post_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    author_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=CandidateStatus.SEEN.value)
    dedup_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_follow_up_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    top_comments_snapshot: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    post_upvotes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=UTC)
    )


class CandidatePostRepository:
    async def create(
        self,
        session: AsyncSession,
        *,
        source_url: str,
        source_time: str,
        source_post_id: str | None,
        author_handle: str | None,
        raw_content: str,
        captured_at: datetime,
        dedup_fingerprint: str,
        top_comments_snapshot: list[dict[str, object]] | None = None,
        post_upvotes: int = 0,
    ) -> CandidatePost:
        candidate = CandidatePost(
            source_url=source_url,
            source_time=source_time,
            source_post_id=source_post_id,
            author_handle=author_handle,
            raw_content=raw_content,
            captured_at=captured_at,
            dedup_fingerprint=dedup_fingerprint,
            top_comments_snapshot=top_comments_snapshot or [],
            post_upvotes=post_upvotes,
            status=CandidateStatus.SEEN.value,
        )
        session.add(candidate)
        await session.flush()
        return candidate

    async def get_by_source_url(self, session: AsyncSession, source_url: str) -> CandidatePost | None:
        statement = select(CandidatePost).where(CandidatePost.source_url == source_url)
        return await session.scalar(statement)

    async def list_active_contents(self, session: AsyncSession) -> list[str]:
        statement = select(CandidatePost.raw_content)
        return list((await session.scalars(statement)).all())

    async def transition_status(
        self,
        session: AsyncSession,
        candidate: CandidatePost,
        target_status: CandidateStatus | str,
    ) -> CandidatePost:
        current = CandidateStatus(candidate.status)
        normalized_target = (
            target_status if isinstance(target_status, CandidateStatus) else CandidateStatus(target_status)
        )
        assert_candidate_transition(current, normalized_target)
        candidate.status = normalized_target.value
        session.add(candidate)
        await session.flush()
        return candidate
