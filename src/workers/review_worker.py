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
from src.services.logging_service import get_logger
from src.services.review_payload_service import ReviewPayloadService

logger = get_logger(__name__)


@dataclass(slots=True)
class ReviewBuildMetrics:
    created_count: int
    skipped_count: int


@dataclass(slots=True)
class ReviewRegenerationMetrics:
    regenerated_count: int
    skipped_count: int
    failed_count: int


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

    async def regenerate_items(
        self,
        session: AsyncSession,
        items: list[ReviewItem],
        *,
        force: bool = False,
    ) -> ReviewRegenerationMetrics:
        regenerated_count = 0
        skipped_count = 0
        failed_count = 0

        for item in items:
            if not force and not self._needs_regeneration(item):
                skipped_count += 1
                continue

            candidate = await session.get(CandidatePost, item.candidate_post_id)
            score = await session.scalar(select(ScoreCard).where(ScoreCard.candidate_post_id == item.candidate_post_id))
            if candidate is None or score is None:
                logger.warning(
                    "review_regeneration_missing_dependencies",
                    review_item_id=item.id,
                    has_candidate=candidate is not None,
                    has_score=score is not None,
                )
                failed_count += 1
                continue

            try:
                payload = await self._payload_service.build_payload(
                    raw_content=candidate.raw_content,
                    risk_score=score.risk_score,
                    is_follow_up=candidate.is_follow_up_candidate,
                    top_comments=self._deserialize_comments(candidate.top_comments_snapshot),
                    final_score=score.final_score,
                    source_url=candidate.source_url,
                )
            except Exception as error:  # pragma: no cover - defensive path
                logger.warning(
                    "review_regeneration_build_failed",
                    review_item_id=item.id,
                    reason=str(error),
                )
                failed_count += 1
                continue

            if not self._regeneration_succeeded(item, payload, force=force):
                logger.warning("review_regeneration_failed", review_item_id=item.id)
                failed_count += 1
                continue

            try:
                await self._review_repo.update_payload(
                    session,
                    review_item_id=item.id,
                    chinese_translation_full=payload.chinese_translation_full,
                    top_comments_translated=payload.top_comments_translated,
                    threads_draft=payload.threads_draft,
                )
            except ValueError as error:
                logger.warning(
                    "review_regeneration_update_failed",
                    review_item_id=item.id,
                    reason=str(error),
                )
                failed_count += 1
                continue

            regenerated_count += 1

        return ReviewRegenerationMetrics(
            regenerated_count=regenerated_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
        )

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

    @staticmethod
    def _is_invalid_draft(draft: str) -> bool:
        """Return True if the draft is empty, a system error placeholder, or exceeds the Threads character limit."""
        stripped = draft.strip()
        if not stripped:
            return True
        if stripped.startswith("【 System:"):
            return True
        if len(stripped) > 500:
            return True
        return False

    @classmethod
    def _needs_regeneration(cls, item: ReviewItem) -> bool:
        return (
            not item.chinese_translation_full.strip()
            or cls._is_invalid_draft(item.threads_draft)
        )

    @classmethod
    def _regeneration_succeeded(cls, item: ReviewItem, payload: Any, *, force: bool) -> bool:
        missing_translation = not item.chinese_translation_full.strip()
        invalid_threads = cls._is_invalid_draft(item.threads_draft)

        if force:
            return any(
                value
                for value in (
                    payload.chinese_translation_full.strip(),
                    payload.top_comments_translated,
                    payload.threads_draft.strip(),
                )
            )

        if missing_translation and not payload.chinese_translation_full.strip():
            return False
        if invalid_threads and cls._is_invalid_draft(payload.threads_draft):
            return False
        return True
