import httpx
import pytest

from src.api import ops_routes
from src.api.app import create_app


@pytest.mark.asyncio
async def test_ops_regenerate_endpoint_returns_metrics(monkeypatch) -> None:
    async def fake_run_regenerate_once(review_item_id: str | None = None) -> dict[str, int]:
        assert review_item_id == "review-123"
        return {"regenerated_count": 1, "skipped_count": 0, "failed_count": 0}

    monkeypatch.setattr(ops_routes, "run_regenerate_once", fake_run_regenerate_once)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/ops/regenerate", params={"review_item_id": "review-123"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "metrics": {"regenerated_count": 1, "skipped_count": 0, "failed_count": 0},
    }


@pytest.mark.asyncio
async def test_ops_regenerate_endpoint_returns_404_for_missing_item(monkeypatch) -> None:
    async def fake_run_regenerate_once(review_item_id: str | None = None) -> dict[str, int]:
        _ = review_item_id
        raise ValueError("Review item not found")

    monkeypatch.setattr(ops_routes, "run_regenerate_once", fake_run_regenerate_once)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/ops/regenerate", params={"review_item_id": "missing"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Review item not found"}
