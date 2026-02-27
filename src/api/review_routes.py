from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_session
from src.models.candidate_post import CandidatePost
from src.models.review_item import ReviewItemRepository
from src.services.audit_service import AuditService

router = APIRouter(tags=["review"])


class ReviewDecisionRequest(BaseModel):
    decision: str
    comment: str | None = None
    reviewedBy: str | None = None


@router.get("/review-items")
async def list_review_items(
    status: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> dict:
    repository = ReviewItemRepository()
    review_items = await repository.list(session, status=status, limit=limit)

    items: list[dict] = []
    for review in review_items:
        candidate = await session.get(CandidatePost, review.candidate_post_id)
        if candidate is None:
            continue
        items.append(
            {
                "id": review.id,
                "candidateId": review.candidate_post_id,
                "englishDraft": review.english_draft,
                "chineseTranslationFull": review.chinese_translation_full,
                "riskTags": review.risk_tags,
                "sourceUrl": candidate.source_url,
                "capturedAt": candidate.captured_at.isoformat(),
                "followUpRationale": review.follow_up_rationale,
                "decision": review.decision,
            }
        )
    return {"items": items}


@router.post("/review-items/{review_item_id}/decision")
async def submit_review_decision(
    review_item_id: str,
    payload: ReviewDecisionRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    repository = ReviewItemRepository()
    audit_service = AuditService()

    try:
        review_item = await repository.decide(
            session,
            review_item_id=review_item_id,
            decision=payload.decision,
            reviewed_by=payload.reviewedBy,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    audit_service.log_review_action(
        review_item_id=review_item.id,
        decision=review_item.decision,
        reviewed_by=review_item.reviewed_by,
    )

    await session.commit()

    return {
        "reviewItemId": review_item.id,
        "decision": review_item.decision,
        "decidedAt": (review_item.reviewed_at or datetime.now(tz=UTC)).isoformat(),
    }
