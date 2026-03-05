from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.moltbook_api_client import MoltbookAPIClient
from src.models.candidate_post import CandidatePost
from src.models.review_item import ReviewItem, ReviewItemRepository
from src.models.score_card import ScoreCard
from src.services.review_payload_service import ReviewPayloadService


@dataclass(slots=True)
class ReviewBuildMetrics:
    created_count: int
    skipped_count: int


class ReviewWorker:
    def __init__(
        self,
        payload_service: ReviewPayloadService | None = None,
        *,
        moltbook_client: MoltbookAPIClient | None = None,
    ) -> None:
        self._payload_service = payload_service or ReviewPayloadService()
        self._review_repo = ReviewItemRepository()
        self._moltbook_client = moltbook_client

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

            top_comments = []
            if self._moltbook_client and candidate.source_post_id:
                top_comments = await self._moltbook_client.fetch_comments(candidate.source_post_id, limit=5, sort="top")

            payload = self._payload_service.build_payload(
                raw_content=candidate.raw_content,
                risk_score=score.risk_score,
                is_follow_up=candidate.is_follow_up_candidate,
                top_comments=top_comments,
                final_score=score.final_score,
                source_url=candidate.source_url,
            )
            await self._review_repo.create(
                session,
                candidate_post_id=candidate.id,
                english_draft=payload.english_draft,
                chinese_translation_full=payload.chinese_translation_full,
                risk_tags=payload.risk_tags,
                top_comments_snapshot=payload.top_comments_snapshot,
                top_comments_translated=payload.top_comments_translated,
                threads_draft=payload.threads_draft,
                follow_up_rationale=payload.follow_up_rationale,
            )
            created_count += 1

        return ReviewBuildMetrics(created_count=created_count, skipped_count=skipped_count)
