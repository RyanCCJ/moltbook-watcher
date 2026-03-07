from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_session
from src.models.candidate_post import CandidatePost
from src.models.review_item import ReviewItemRepository
from src.models.score_card import ScoreCardRepository
from src.services.audit_service import AuditService

router = APIRouter(tags=["review"])


class ReviewDecisionRequest(BaseModel):
    decision: str
    comment: str | None = None
    reviewedBy: str | None = None


class ReviewDraftUpdateRequest(BaseModel):
    threadsDraft: str


@router.get("/review-items")
async def list_review_items(
    status: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> dict:
    repository = ReviewItemRepository()
    score_repository = ScoreCardRepository()
    review_items = await repository.list(session, status=status, limit=limit)

    items: list[dict] = []
    for review in review_items:
        candidate = await session.get(CandidatePost, review.candidate_post_id)
        if candidate is None:
            continue
        score = await score_repository.get_by_candidate(session, review.candidate_post_id)
        ai_score = None
        if score is not None:
            ai_score = {
                "noveltyScore": score.novelty_score,
                "depthScore": score.depth_score,
                "tensionScore": score.tension_score,
                "reflectiveImpactScore": score.reflective_impact_score,
                "engagementScore": score.engagement_score,
                "riskScore": score.risk_score,
                "contentScore": score.content_score,
                "finalScore": score.final_score,
                "scoreVersion": score.score_version,
                "scoredAt": score.scored_at.isoformat(),
            }
        items.append(
            {
                "id": review.id,
                "candidateId": review.candidate_post_id,
                "draftContent": review.english_draft,
                "translatedContent": review.chinese_translation_full,
                "threadsDraft": review.threads_draft,
                "topCommentsSnapshot": review.top_comments_snapshot,
                "topCommentsTranslated": review.top_comments_translated,
                "aiScore": ai_score,
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


@router.patch("/review-items/{review_item_id}/draft")
async def update_review_draft(
    review_item_id: str,
    payload: ReviewDraftUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    repository = ReviewItemRepository()

    try:
        review_item = await repository.update_draft(
            session,
            review_item_id=review_item_id,
            threads_draft=payload.threadsDraft,
        )
    except ValueError as error:
        message = str(error)
        if message == "Review item not found":
            raise HTTPException(status_code=404, detail=message) from error
        if message == "Decision already submitted":
            raise HTTPException(status_code=409, detail=message) from error
        raise HTTPException(status_code=400, detail=message) from error

    await session.commit()
    return {"reviewItemId": review_item.id, "updated": True}
