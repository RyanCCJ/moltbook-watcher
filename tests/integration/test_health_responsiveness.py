import asyncio
import json
import time

import httpx
import pytest

from src.api import ops_routes
from src.api.app import create_app
from src.services.scoring_service import ScoringService


@pytest.mark.asyncio
async def test_health_endpoint_responds_while_ingestion_is_running(monkeypatch) -> None:
    async def slow_ingestion(**_kwargs) -> dict[str, int]:
        def handler(_request: httpx.Request) -> httpx.Response:
            time.sleep(0.25)
            return httpx.Response(
                200,
                json={
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "novelty": 4.0,
                                "depth": 4.0,
                                "tension": 4.0,
                                "reflective_impact": 4.0,
                                "engagement": 4.0,
                                "risk": 1,
                            }
                        ),
                    }
                },
            )

        service = ScoringService(ollama_client=httpx.Client(transport=httpx.MockTransport(handler)))
        await service.score_candidate("slow ingestion content", {"likes": 1})
        service.close()
        return {
            "fetched_count": 1,
            "persisted_count": 1,
            "filtered_duplicate_count": 0,
            "review_items_created": 0,
        }

    monkeypatch.setattr(ops_routes, "run_ingestion_once", slow_ingestion)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ingestion_task = asyncio.create_task(client.post("/ops/ingestion/run", params={"limit": 1}))
        await asyncio.sleep(0.02)

        start = time.perf_counter()
        health_response = await client.get("/health")
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        ingestion_response = await ingestion_task

    assert health_response.status_code == 200
    assert health_response.json()["status"] in {"ok", "degraded"}
    assert elapsed_ms < 150
    assert ingestion_response.status_code == 200
