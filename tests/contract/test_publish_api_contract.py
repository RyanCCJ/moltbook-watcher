from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.app import create_app
from src.models.base import Base, get_session
from src.models.candidate_post import CandidatePost
from src.models.publish_job import PublishJob


@pytest.mark.asyncio
async def test_publish_mode_pause_and_jobs_endpoints_follow_contract() -> None:
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
            source_url="https://moltbook.com/p/publish-1",
            source_window="today",
            source_post_id="publish-1",
            author_handle="alice",
            raw_content="Publish me",
            captured_at=datetime.now(tz=UTC),
            status="scheduled",
            dedup_fingerprint="hash-1",
        )
        session.add(candidate)
        await session.flush()

        session.add(
            PublishJob(
                candidate_post_id=candidate.id,
                threads_account_key="account-1",
                scheduled_for=datetime.now(tz=UTC),
                status="scheduled",
                attempt_count=0,
                max_attempts=3,
            )
        )
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        mode_response = await client.put(
            "/publishing/mode",
            json={"mode": "low-risk-auto", "reason": "test"},
        )
        pause_response = await client.post("/publishing/pause")
        jobs_response = await client.get("/publish-jobs", params={"status": "scheduled"})

    assert mode_response.status_code == 200
    assert mode_response.json()["mode"] == "low-risk-auto"

    assert pause_response.status_code == 202

    assert jobs_response.status_code == 200
    payload = jobs_response.json()
    assert payload["items"][0]["status"] == "scheduled"
    assert payload["items"][0]["maxAttempts"] == 3
