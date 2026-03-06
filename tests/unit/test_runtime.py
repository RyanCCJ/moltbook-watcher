from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models.base import Base
from src.models.candidate_post import CandidatePost
from src.workers import runtime


class _NoopMoltbookClient:
    def __init__(self, *args, **kwargs) -> None:
        _ = (args, kwargs)

    async def close(self) -> None:
        return None


class _NoopScoringService:
    def __init__(self, *args, **kwargs) -> None:
        _ = (args, kwargs)

    def close(self) -> None:
        return None


class _NoopPayloadService:
    def __init__(self, *args, **kwargs) -> None:
        _ = (args, kwargs)

    def close(self) -> None:
        return None


class _IngestionWorker:
    def __init__(self, *args, **kwargs) -> None:
        _ = (args, kwargs)

    async def run_cycle(self, session, window: str, limit: int, sort: str):
        _ = (window, limit, sort)
        candidate = CandidatePost(
            source_url="https://www.moltbook.com/post/runtime-1",
            source_window="today",
            source_post_id="runtime-1",
            author_handle="runtime",
            raw_content="runtime candidate",
            captured_at=datetime.now(tz=UTC),
            status="queued",
            dedup_fingerprint="runtime-hash",
            top_comments_snapshot=[],
        )
        session.add(candidate)
        await session.flush()
        return SimpleNamespace(fetched_count=1, persisted_count=1, filtered_duplicate_count=0)


class _FailingReviewWorker:
    def __init__(self, *args, **kwargs) -> None:
        _ = (args, kwargs)

    async def run_cycle(self, session):
        _ = session
        raise RuntimeError("review exploded")


@pytest.mark.asyncio
async def test_run_ingestion_once_keeps_ingestion_data_when_review_fails(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime_split.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(runtime, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(runtime, "MoltbookAPIClient", _NoopMoltbookClient)
    monkeypatch.setattr(runtime, "ScoringService", _NoopScoringService)
    monkeypatch.setattr(runtime, "ReviewPayloadService", _NoopPayloadService)
    monkeypatch.setattr(runtime, "IngestionWorker", _IngestionWorker)
    monkeypatch.setattr(runtime, "ReviewWorker", _FailingReviewWorker)
    monkeypatch.setattr(
        runtime,
        "get_settings",
        lambda: SimpleNamespace(
            moltbook_api_base_url="https://api.test",
            moltbook_api_token="token",
            ollama_base_url="http://ollama",
            ollama_model="test-model",
            translation_language="",
            threads_language="en",
        ),
    )

    with pytest.raises(runtime.ReviewCycleError, match="review exploded"):
        await runtime.run_ingestion_once(window="today", limit=5, sort="top")

    async with session_factory() as session:
        candidates = (await session.scalars(select(CandidatePost))).all()

    assert len(candidates) == 1
    assert candidates[0].source_post_id == "runtime-1"
