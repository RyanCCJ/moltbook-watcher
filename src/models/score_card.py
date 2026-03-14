from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class ScoreCard(Base):
    __tablename__ = "score_cards"
    __table_args__ = (UniqueConstraint("candidate_post_id", name="uq_score_card_candidate"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    candidate_post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidate_posts.id", ondelete="CASCADE"), nullable=False
    )
    novelty_score: Mapped[float] = mapped_column(Float, nullable=False)
    depth_score: Mapped[float] = mapped_column(Float, nullable=False)
    tension_score: Mapped[float] = mapped_column(Float, nullable=False)
    reflective_impact_score: Mapped[float] = mapped_column(Float, nullable=False)
    engagement_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    content_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    route_decision: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    score_version: Mapped[str] = mapped_column(String(64), nullable=False)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=UTC)
    )


class ScoreCardRepository:
    async def create(
        self,
        session: AsyncSession,
        *,
        candidate_post_id: str,
        novelty_score: float,
        depth_score: float,
        tension_score: float,
        reflective_impact_score: float,
        engagement_score: float,
        risk_score: int,
        content_score: float,
        final_score: float,
        route_decision: str | None = None,
        score_version: str,
    ) -> ScoreCard:
        score_card = ScoreCard(
            candidate_post_id=candidate_post_id,
            novelty_score=novelty_score,
            depth_score=depth_score,
            tension_score=tension_score,
            reflective_impact_score=reflective_impact_score,
            engagement_score=engagement_score,
            risk_score=risk_score,
            content_score=content_score,
            final_score=final_score,
            route_decision=route_decision,
            score_version=score_version,
        )
        session.add(score_card)
        await session.flush()
        return score_card

    async def get_by_candidate(self, session: AsyncSession, candidate_post_id: str) -> ScoreCard | None:
        statement = select(ScoreCard).where(ScoreCard.candidate_post_id == candidate_post_id)
        return await session.scalar(statement)
