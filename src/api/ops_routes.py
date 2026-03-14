from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from src.config.settings import get_settings
from src.workers.runtime import run_ingestion_once, run_publish_once, run_regenerate_once

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


@router.post("/regenerate")
async def run_regenerate(review_item_id: str | None = Query(default=None)) -> dict[str, object]:
    try:
        metrics = await run_regenerate_once(review_item_id=review_item_id)
    except ValueError as error:
        if str(error) == "Review item not found":
            raise HTTPException(status_code=404, detail="Review item not found") from error
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"regenerate_failed: {error}") from error
    return {"ok": True, "metrics": metrics}
