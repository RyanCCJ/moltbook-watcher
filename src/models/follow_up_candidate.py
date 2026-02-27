from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class FollowUpCandidate(Base):
    __tablename__ = "follow_up_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    candidate_post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidate_posts.id", ondelete="CASCADE"), nullable=False
    )
    prior_published_post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("published_post_records.id", ondelete="CASCADE"), nullable=False
    )
    novelty_delta_score: Mapped[float] = mapped_column(Float, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    eligible_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=UTC)
    )


class FollowUpCandidateRepository:
    async def create(
        self,
        session: AsyncSession,
        *,
        candidate_post_id: str,
        prior_published_post_id: str,
        novelty_delta_score: float,
        justification: str,
        eligible_after: datetime,
        is_eligible: bool,
    ) -> FollowUpCandidate:
        candidate = FollowUpCandidate(
            candidate_post_id=candidate_post_id,
            prior_published_post_id=prior_published_post_id,
            novelty_delta_score=novelty_delta_score,
            justification=justification,
            eligible_after=eligible_after,
            is_eligible=is_eligible,
        )
        session.add(candidate)
        await session.flush()
        return candidate

    async def list_eligible(self, session: AsyncSession) -> list[FollowUpCandidate]:
        statement = select(FollowUpCandidate).where(FollowUpCandidate.is_eligible.is_(True))
        return list((await session.scalars(statement)).all())
