from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.app import create_app
from src.models.base import Base, get_session
from src.models.candidate_post import CandidatePostRepository
from src.models.review_item import ReviewItem, ReviewItemRepository


async def _build_app_with_review_item(decision: str = "pending") -> tuple[object, str, async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    app = create_app()

    async def override_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    candidate_repo = CandidatePostRepository()
    review_repo = ReviewItemRepository()

    async with async_session() as session:
        candidate = await candidate_repo.create(
            session,
            source_url="https://moltbook.com/p/draft",
            source_time="day",
            source_post_id="draft-item",
            author_handle="reviewer",
            raw_content="Draft payload",
            captured_at=datetime.now(tz=UTC),
            dedup_fingerprint="draft-hash",
        )
        await candidate_repo.transition_status(session, candidate, target_status="scored")
        await candidate_repo.transition_status(session, candidate, target_status="queued")
        review_item = await review_repo.create(
            session,
            candidate_post_id=candidate.id,
            english_draft="Draft",
            chinese_translation_full="Draft translation",
            risk_tags=[],
            threads_draft="old draft",
        )
        if decision != "pending":
            await review_repo.decide(
                session,
                review_item_id=review_item.id,
                decision=decision,
                reviewed_by="operator",
            )
        await session.commit()

    return app, review_item.id, async_session


@pytest.mark.asyncio
async def test_review_draft_patch_endpoint_success() -> None:
    app, review_item_id, async_session = await _build_app_with_review_item()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/review-items/{review_item_id}/draft",
            json={"threadsDraft": "new draft text"},
        )

    assert response.status_code == 200
    assert response.json() == {"reviewItemId": review_item_id, "updated": True}

    async with async_session() as session:
        persisted = await session.scalar(select(ReviewItem).where(ReviewItem.id == review_item_id))

    assert persisted is not None
    assert persisted.threads_draft == "new draft text"


@pytest.mark.asyncio
async def test_review_draft_patch_endpoint_returns_404_for_missing_item() -> None:
    app, _, _ = await _build_app_with_review_item()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            "/review-items/missing/draft",
            json={"threadsDraft": "new draft text"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Review item not found"


@pytest.mark.asyncio
async def test_review_draft_patch_endpoint_returns_409_for_decided_item() -> None:
    app, review_item_id, _ = await _build_app_with_review_item(decision="approved")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/review-items/{review_item_id}/draft",
            json={"threadsDraft": "new draft text"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Decision already submitted"
