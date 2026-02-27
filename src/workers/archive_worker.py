from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.candidate_post import CandidatePost, CandidatePostRepository
from src.models.lifecycle import CandidateStatus
from src.models.review_item import ReviewItem, ReviewItemRepository
from src.models.score_card import ScoreCard


class ArchiveWorker:
    def __init__(self) -> None:
        self._candidate_repo = CandidatePostRepository()
        self._review_repo = ReviewItemRepository()

    async def archive_stale_review_items(self, session: AsyncSession, max_age_days: int = 14) -> int:
        cutoff = datetime.now(tz=UTC) - timedelta(days=max_age_days)
        statement = (
            select(ReviewItem)
            .join(CandidatePost, CandidatePost.id == ReviewItem.candidate_post_id)
            .where(ReviewItem.decision == "pending")
            .where(CandidatePost.status == CandidateStatus.QUEUED.value)
            .where(CandidatePost.captured_at < cutoff)
        )
        stale_items = list((await session.scalars(statement)).all())

        for item in stale_items:
            await self._review_repo.decide(
                session,
                review_item_id=item.id,
                decision="archived",
                reviewed_by="archive-worker",
            )

        return len(stale_items)

    async def build_high_score_recall(self, session: AsyncSession, min_score: float = 4.0) -> list[dict]:
        statement = (
            select(CandidatePost, ScoreCard)
            .join(ScoreCard, ScoreCard.candidate_post_id == CandidatePost.id)
            .where(CandidatePost.status == CandidateStatus.ARCHIVED.value)
            .where(ScoreCard.final_score >= min_score)
            .order_by(ScoreCard.final_score.desc())
        )
        rows = (await session.execute(statement)).all()

        return [
            {
                "candidate_id": candidate.id,
                "source_url": candidate.source_url,
                "final_score": score.final_score,
            }
            for candidate, score in rows
        ]
