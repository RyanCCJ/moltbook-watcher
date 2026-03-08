from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import get_settings
from src.integrations.moltbook_api_client import MoltbookComment
from src.models.candidate_post import CandidatePost
from src.models.lifecycle import CandidateStatus, ReviewDecision
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
    ) -> None:
        settings = get_settings()
        self._payload_service = payload_service or ReviewPayloadService(
            threads_draft_min_score=settings.review_min_score
        )
        self._review_repo = ReviewItemRepository()

    async def run_cycle(self, session: AsyncSession) -> ReviewBuildMetrics:
        statement = (
            select(CandidatePost, ScoreCard)
            .join(ScoreCard, ScoreCard.candidate_post_id == CandidatePost.id)
            .outerjoin(ReviewItem, ReviewItem.candidate_post_id == CandidatePost.id)
            .where(CandidatePost.status.in_([CandidateStatus.QUEUED.value, CandidateStatus.APPROVED.value]))
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

            top_comments = self._deserialize_comments(candidate.top_comments_snapshot)

            payload = await self._payload_service.build_payload(
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
                decision=(
                    ReviewDecision.APPROVED.value
                    if candidate.status == CandidateStatus.APPROVED.value
                    else ReviewDecision.PENDING.value
                ),
                reviewed_by="semi-auto" if candidate.status == CandidateStatus.APPROVED.value else None,
            )
            created_count += 1

        return ReviewBuildMetrics(created_count=created_count, skipped_count=skipped_count)

    @staticmethod
    def _deserialize_comments(snapshot: list[dict[str, Any]] | None) -> list[MoltbookComment]:
        comments: list[MoltbookComment] = []
        for item in snapshot or []:
            if not isinstance(item, dict):
                continue
            content_text = str(item.get("content_text", "")).strip()
            if not content_text:
                continue
            upvotes_value = item.get("upvotes", 0)
            try:
                upvotes = int(upvotes_value)
            except (TypeError, ValueError):
                upvotes = 0
            comments.append(
                MoltbookComment(
                    author_handle=item.get("author_handle"),
                    content_text=content_text,
                    upvotes=max(0, upvotes),
                )
            )
        return comments
