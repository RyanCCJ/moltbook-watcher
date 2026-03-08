from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.candidate_post import CandidatePost
from src.models.lifecycle import ReviewDecision
from src.models.published_post_record import PublishedPostRecord
from src.models.review_item import ReviewItem, ReviewItemRepository
from src.models.score_card import ScoreCardRepository


async def load_review_item_payloads(
    session: AsyncSession,
    *,
    status: str,
    limit: int,
) -> list[dict[str, Any]]:
    review_items = await ReviewItemRepository().list(session, status=status, limit=limit)
    score_repo = ScoreCardRepository()
    items: list[dict[str, Any]] = []
    for review in review_items:
        candidate = await session.get(CandidatePost, review.candidate_post_id)
        if candidate is None:
            continue
        score = await score_repo.get_by_candidate(session, review.candidate_post_id)
        ai_score = None
        if score is not None:
            ai_score = {"finalScore": score.final_score}
        items.append(
            {
                "id": review.id,
                "draftContent": review.english_draft,
                "translatedContent": review.chinese_translation_full,
                "threadsDraft": review.threads_draft,
                "topCommentsSnapshot": review.top_comments_snapshot,
                "topCommentsTranslated": review.top_comments_translated,
                "aiScore": ai_score,
                "riskTags": review.risk_tags,
                "sourceUrl": candidate.source_url,
                "followUpRationale": review.follow_up_rationale,
                "decision": review.decision,
            }
        )
    return items


async def build_stats_payload(
    session: AsyncSession,
    *,
    archived_count: int = 0,
    high_score_recalls: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    start_of_day = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    pending_count = await session.scalar(
        select(func.count()).select_from(ReviewItem).where(ReviewItem.decision == ReviewDecision.PENDING.value)
    )
    approved_today_count = await session.scalar(
        select(func.count())
        .select_from(ReviewItem)
        .where(ReviewItem.decision == ReviewDecision.APPROVED.value)
        .where(ReviewItem.reviewed_at >= start_of_day)
    )
    rejected_today_count = await session.scalar(
        select(func.count())
        .select_from(ReviewItem)
        .where(ReviewItem.decision == ReviewDecision.REJECTED.value)
        .where(ReviewItem.reviewed_at >= start_of_day)
    )
    published_today_count = await session.scalar(
        select(func.count())
        .select_from(PublishedPostRecord)
        .where(PublishedPostRecord.published_at >= start_of_day)
    )
    top_pending = await load_review_item_payloads(session, status=ReviewDecision.PENDING.value, limit=20)
    top_pending.sort(key=lambda item: float((item.get("aiScore") or {}).get("finalScore") or 0), reverse=True)
    return {
        "pendingCount": pending_count or 0,
        "approvedTodayCount": approved_today_count or 0,
        "rejectedTodayCount": rejected_today_count or 0,
        "publishedTodayCount": published_today_count or 0,
        "archivedCount": archived_count,
        "highScoreRecalls": high_score_recalls or [],
        "topPendingItems": top_pending[:3],
    }
