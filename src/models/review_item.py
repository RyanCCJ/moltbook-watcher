from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.models.candidate_post import CandidatePost, CandidatePostRepository
from src.models.lifecycle import CandidateStatus, ReviewDecision


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (UniqueConstraint("candidate_post_id", name="uq_review_candidate"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    candidate_post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidate_posts.id", ondelete="CASCADE"), nullable=False
    )
    english_draft: Mapped[str] = mapped_column(Text, nullable=False)
    chinese_translation_full: Mapped[str] = mapped_column(Text, nullable=False)
    risk_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    follow_up_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default=ReviewDecision.PENDING.value)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=UTC)
    )


class ReviewItemRepository:
    def __init__(self) -> None:
        self._candidate_repo = CandidatePostRepository()

    async def create(
        self,
        session: AsyncSession,
        *,
        candidate_post_id: str,
        english_draft: str,
        chinese_translation_full: str,
        risk_tags: list[str],
        follow_up_rationale: str | None = None,
    ) -> ReviewItem:
        review_item = ReviewItem(
            candidate_post_id=candidate_post_id,
            english_draft=english_draft,
            chinese_translation_full=chinese_translation_full,
            risk_tags=risk_tags,
            follow_up_rationale=follow_up_rationale,
            decision=ReviewDecision.PENDING.value,
        )
        session.add(review_item)
        await session.flush()
        return review_item

    async def get(self, session: AsyncSession, review_item_id: str) -> ReviewItem | None:
        statement = select(ReviewItem).where(ReviewItem.id == review_item_id)
        return await session.scalar(statement)

    async def list(
        self,
        session: AsyncSession,
        *,
        status: str | None = None,
        limit: int = 10,
    ) -> list[ReviewItem]:
        statement = select(ReviewItem).order_by(ReviewItem.created_at.desc()).limit(limit)
        if status:
            statement = statement.where(ReviewItem.decision == status)
        return list((await session.scalars(statement)).all())

    async def decide(
        self,
        session: AsyncSession,
        *,
        review_item_id: str,
        decision: str,
        reviewed_by: str | None,
    ) -> ReviewItem:
        review_item = await self.get(session, review_item_id)
        if review_item is None:
            raise ValueError("Review item not found")
        if review_item.decision != ReviewDecision.PENDING.value:
            raise ValueError("Decision already submitted")
        if decision not in {
            ReviewDecision.APPROVED.value,
            ReviewDecision.REJECTED.value,
            ReviewDecision.ARCHIVED.value,
        }:
            raise ValueError("Invalid decision")

        candidate = await session.get(CandidatePost, review_item.candidate_post_id)
        if candidate is None:
            raise ValueError("Candidate post not found")

        await self._candidate_repo.transition_status(session, candidate, CandidateStatus.REVIEWED)
        target = {
            ReviewDecision.APPROVED.value: CandidateStatus.APPROVED,
            ReviewDecision.REJECTED.value: CandidateStatus.REJECTED,
            ReviewDecision.ARCHIVED.value: CandidateStatus.ARCHIVED,
        }[decision]
        await self._candidate_repo.transition_status(session, candidate, target)

        review_item.decision = decision
        review_item.reviewed_by = reviewed_by
        review_item.reviewed_at = datetime.now(tz=UTC)
        session.add(review_item)
        await session.flush()

        return review_item
