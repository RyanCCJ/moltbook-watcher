from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.candidate_post import CandidatePost
from src.models.review_item import ReviewItem, ReviewItemRepository
from src.models.score_card import ScoreCard
from src.services.review_payload_service import ReviewPayloadService


@dataclass(slots=True)
class ReviewBuildMetrics:
    created_count: int
    skipped_count: int


class ReviewWorker:
    def __init__(self, payload_service: ReviewPayloadService | None = None) -> None:
        self._payload_service = payload_service or ReviewPayloadService()
        self._review_repo = ReviewItemRepository()

    async def run_cycle(self, session: AsyncSession) -> ReviewBuildMetrics:
        statement = (
            select(CandidatePost, ScoreCard)
            .join(ScoreCard, ScoreCard.candidate_post_id == CandidatePost.id)
            .outerjoin(ReviewItem, ReviewItem.candidate_post_id == CandidatePost.id)
            .where(CandidatePost.status == "queued")
            .where(ReviewItem.id.is_(None))
            .order_by(CandidatePost.captured_at.desc())
        )
        rows = (await session.execute(statement)).all()

        created_count = 0
        skipped_count = 0
        for candidate, score in rows:
            if not candidate.raw_content.strip():
                skipped_count += 1
                continue

            payload = self._payload_service.build_payload(
                raw_content=candidate.raw_content,
                risk_score=score.risk_score,
                is_follow_up=candidate.is_follow_up_candidate,
            )
            await self._review_repo.create(
                session,
                candidate_post_id=candidate.id,
                english_draft=payload.english_draft,
                chinese_translation_full=payload.chinese_translation_full,
                risk_tags=payload.risk_tags,
                follow_up_rationale=payload.follow_up_rationale,
            )
            created_count += 1

        return ReviewBuildMetrics(created_count=created_count, skipped_count=skipped_count)
