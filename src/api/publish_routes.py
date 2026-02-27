from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_session
from src.models.publish_job import PublishJobRepository
from src.services.audit_service import AuditService
from src.services.publish_mode_service import publish_control

router = APIRouter(tags=["publish"])


class PublishModeRequest(BaseModel):
    mode: str
    reason: str | None = None


@router.put("/publishing/mode")
async def switch_mode(payload: PublishModeRequest) -> dict:
    previous_mode = publish_control.mode
    try:
        publish_control.switch_mode(payload.mode, reason=payload.reason)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    AuditService().log_mode_change(from_mode=previous_mode, to_mode=publish_control.mode, reason=payload.reason)
    return {"mode": publish_control.mode}


@router.post("/publishing/pause", status_code=202)
async def pause_publishing() -> dict:
    publish_control.pause()
    return {"paused": True}


@router.get("/publish-jobs")
async def list_publish_jobs(
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    jobs = await PublishJobRepository().list(session, status=status)
    items = [
        {
            "id": job.id,
            "candidateId": job.candidate_post_id,
            "scheduledFor": job.scheduled_for.isoformat(),
            "status": job.status,
            "attemptCount": job.attempt_count,
            "maxAttempts": job.max_attempts,
            "lastErrorCode": job.last_error_code,
            "lastErrorMessage": job.last_error_message,
        }
        for job in jobs
    ]
    return {"items": items}
