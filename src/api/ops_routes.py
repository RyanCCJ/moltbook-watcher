from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from src.config.settings import get_settings
from src.workers.runtime import run_ingestion_once, run_publish_once

router = APIRouter(prefix="/ops", tags=["ops"])
settings = get_settings()


@router.post("/ingestion/run")
async def run_ingestion(
    time: str = Query(default=settings.ingestion_time, pattern="^(hour|day|week|month|all)$"),
    sort: str = Query(default=settings.ingestion_sort, pattern="^(hot|new|top|rising)$"),
    limit: int = Query(default=settings.ingestion_limit, ge=1, le=200),
) -> dict[str, object]:
    try:
        metrics = await run_ingestion_once(time=time, limit=limit, sort=sort)
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"ingestion_failed: {error}") from error
    return {"ok": True, "metrics": metrics}


@router.post("/publish/run")
async def run_publish() -> dict[str, object]:
    try:
        metrics = await run_publish_once()
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"publish_failed: {error}") from error
    return {"ok": True, "metrics": metrics}
