from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.app import create_app
from src.models.base import Base, get_session
from src.models.candidate_post import CandidatePost
from src.models.review_item import ReviewItem
from src.models.score_card import ScoreCard


@pytest.mark.asyncio
async def test_review_list_and_decision_endpoints_follow_contract() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    app = create_app()

    async def override_session():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    async with async_session() as session:
        candidate = CandidatePost(
            source_url="https://moltbook.com/p/10",
            source_window="today",
            source_post_id="10",
            author_handle="reviewer",
            raw_content="Operator-focused review payload",
            captured_at=datetime.now(tz=UTC),
            status="queued",
            dedup_fingerprint="abc",
        )
        session.add(candidate)
        await session.flush()

        review_item = ReviewItem(
            candidate_post_id=candidate.id,
            english_draft="Draft",
            chinese_translation_full="Draft translation",
            risk_tags="[]",
            follow_up_rationale=None,
            decision="pending",
        )
        session.add(review_item)
        session.add(
            ScoreCard(
                candidate_post_id=candidate.id,
                novelty_score=4.3,
                depth_score=4.1,
                tension_score=3.2,
                reflective_impact_score=4.0,
                engagement_score=3.6,
                risk_score=1,
                content_score=3.84,
                final_score=3.64,
                score_version="contract-v1",
            )
        )
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        list_response = await client.get("/review-items", params={"status": "pending", "limit": 10})
        assert list_response.status_code == 200

        payload = list_response.json()
        assert "items" in payload
        assert payload["items"][0]["englishDraft"] == "Draft"
        assert payload["items"][0]["aiScore"]["finalScore"] == 3.64
        assert payload["items"][0]["aiScore"]["scoreVersion"] == "contract-v1"

        decision_response = await client.post(
            f"/review-items/{review_item.id}/decision",
            json={"decision": "approved", "reviewedBy": "operator"},
        )

    assert decision_response.status_code == 200
    decision_payload = decision_response.json()
    assert decision_payload["reviewItemId"] == review_item.id
    assert decision_payload["decision"] == "approved"
