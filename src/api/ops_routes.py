from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from src.workers.runtime import run_ingestion_once, run_publish_once

router = APIRouter(prefix="/ops", tags=["ops"])


@router.post("/ingestion/run")
async def run_ingestion(
    window: str = Query(default="past_hour"),
    sort: str = Query(default="top"),
    limit: int = Query(default=20, ge=1, le=200),
) -> dict[str, object]:
    try:
        metrics = await run_ingestion_once(window=window, limit=limit, sort=sort)
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
