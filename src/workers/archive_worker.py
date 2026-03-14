from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.candidate_post import CandidatePost, CandidatePostRepository
from src.models.lifecycle import CandidateStatus, ReviewDecision
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
            .where(ReviewItem.decision == ReviewDecision.PENDING.value)
            .where(CandidatePost.status == CandidateStatus.QUEUED.value)
            .where(CandidatePost.captured_at < cutoff)
        )
        stale_items = list((await session.scalars(statement)).all())

        for item in stale_items:
            await self._review_repo.decide(
                session,
                review_item_id=item.id,
                decision=ReviewDecision.ARCHIVED.value,
                reviewed_by="archive-worker",
            )

        return len(stale_items)

    async def build_high_score_recall(
        self,
        session: AsyncSession,
        min_score: float = 4.0,
    ) -> list[dict[str, object]]:
        statement = (
            select(CandidatePost, ReviewItem, ScoreCard)
            .join(ReviewItem, ReviewItem.candidate_post_id == CandidatePost.id)
            .join(ScoreCard, ScoreCard.candidate_post_id == CandidatePost.id)
            .where(CandidatePost.status == CandidateStatus.ARCHIVED.value)
            .where(ReviewItem.decision == ReviewDecision.ARCHIVED.value)
            .where(ReviewItem.reviewed_by == "archive-worker")
            .where(ScoreCard.final_score >= min_score)
            .order_by(ScoreCard.final_score.desc())
            .limit(10)
        )
        rows = (await session.execute(statement)).all()

        return [self._serialize_recall_item(candidate, review_item, score) for candidate, review_item, score in rows]

    async def build_todays_high_score_recall(self, session: AsyncSession) -> list[dict[str, object]]:
        start_of_day = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        statement = (
            select(CandidatePost, ReviewItem, ScoreCard)
            .join(ReviewItem, ReviewItem.candidate_post_id == CandidatePost.id)
            .join(ScoreCard, ScoreCard.candidate_post_id == CandidatePost.id)
            .where(CandidatePost.status == CandidateStatus.ARCHIVED.value)
            .where(ReviewItem.decision == ReviewDecision.ARCHIVED.value)
            .where(ReviewItem.reviewed_by == "archive-worker")
            .where(ReviewItem.reviewed_at >= start_of_day)
            .where(ScoreCard.final_score >= 4.0)
            .order_by(ScoreCard.final_score.desc())
        )
        rows = (await session.execute(statement)).all()

        return [self._serialize_recall_item(candidate, review_item, score) for candidate, review_item, score in rows]

    async def recall_item(self, session: AsyncSession, review_item_id: str) -> str:
        review_item = await self._review_repo.get(session, review_item_id)
        if review_item is None:
            return "not_eligible"

        candidate = await session.get(CandidatePost, review_item.candidate_post_id)
        if candidate is None:
            return "not_eligible"

        if (
            review_item.decision == ReviewDecision.PENDING.value
            and review_item.reviewed_by is None
            and review_item.reviewed_at is None
            and candidate.status == CandidateStatus.QUEUED.value
        ):
            return "already_recalled"

        if review_item.reviewed_by != "archive-worker":
            return "not_eligible"

        if (
            review_item.decision != ReviewDecision.ARCHIVED.value
            or candidate.status != CandidateStatus.ARCHIVED.value
        ):
            return "already_recalled"

        await self._candidate_repo.transition_status(session, candidate, CandidateStatus.QUEUED)
        review_item.decision = ReviewDecision.PENDING.value
        review_item.reviewed_by = None
        review_item.reviewed_at = None
        session.add(review_item)
        await session.flush()
        return "recalled"

    def _serialize_recall_item(
        self,
        candidate: CandidatePost,
        review_item: ReviewItem,
        score: ScoreCard,
    ) -> dict[str, object]:
        title = review_item.english_draft.strip() or review_item.threads_draft.strip() or candidate.raw_content.strip()
        return {
            "candidateId": candidate.id,
            "reviewItemId": review_item.id,
            "title": title,
            "sourceUrl": candidate.source_url,
            "finalScore": score.final_score,
        }
