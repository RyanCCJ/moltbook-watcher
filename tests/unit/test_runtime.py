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

    async def run_cycle(self, session, time: str, limit: int, sort: str):
        _ = (time, limit, sort)
        candidate = CandidatePost(
            source_url="https://www.moltbook.com/post/runtime-1",
            source_time="day",
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
        return SimpleNamespace(
            fetched_count=1,
            persisted_count=1,
            scored_count=1,
            queued_count=1,
            archived_count=0,
            auto_approved_count=0,
            fast_track_count=0,
            filtered_duplicate_count=0,
            score_breakdown={"auto_publish": 0, "review_queue": 1, "archived": 0},
            risk_breakdown={"low": 1, "medium": 0, "high": 0},
        )


class _FailingReviewWorker:
    def __init__(self, *args, **kwargs) -> None:
        _ = (args, kwargs)

    async def run_cycle(self, session):
        _ = session
        raise RuntimeError("review exploded")


class _SuccessfulReviewWorker:
    def __init__(self, *args, **kwargs) -> None:
        _ = (args, kwargs)

    async def run_cycle(self, session):
        _ = session
        return SimpleNamespace(created_count=1, skipped_count=0)


class _StubSession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


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
            review_min_score=3.5,
            auto_publish_min_score=4.0,
            ingestion_time="hour",
            ingestion_limit=20,
            ingestion_sort="top",
        ),
    )

    with pytest.raises(runtime.ReviewCycleError, match="review exploded"):
        await runtime.run_ingestion_once(time="day", limit=5, sort="top")

    async with session_factory() as session:
        candidates = (await session.scalars(select(CandidatePost))).all()

    assert len(candidates) == 1
    assert candidates[0].source_post_id == "runtime-1"


@pytest.mark.asyncio
async def test_run_ingestion_once_sends_ingestion_digest_to_telegram(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime_telegram.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    sent_messages: list[tuple[str, str]] = []

    class _StubTelegramClient:
        async def send_message(self, chat_id: str, text: str, reply_markup=None) -> None:
            _ = reply_markup
            sent_messages.append((chat_id, text))

        async def close(self) -> None:
            return None

    class _StubTelegramService:
        def __init__(self, telegram_client, chat_id: str) -> None:
            _ = (telegram_client, chat_id)

        def format_ingestion_digest(self, **kwargs) -> str:
            return f"digest:{kwargs['persisted_count']}:{kwargs['pending_total']}"

    monkeypatch.setattr(runtime, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(runtime, "MoltbookAPIClient", _NoopMoltbookClient)
    monkeypatch.setattr(runtime, "ScoringService", _NoopScoringService)
    monkeypatch.setattr(runtime, "ReviewPayloadService", _NoopPayloadService)
    monkeypatch.setattr(runtime, "IngestionWorker", _IngestionWorker)
    monkeypatch.setattr(runtime, "ReviewWorker", _SuccessfulReviewWorker)
    monkeypatch.setattr(runtime, "TelegramClient", lambda bot_token: _StubTelegramClient())
    monkeypatch.setattr(runtime, "TelegramService", _StubTelegramService)
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
            telegram_enabled=True,
            telegram_bot_token="telegram-token",
            telegram_chat_id="12345",
            review_min_score=3.5,
            auto_publish_min_score=4.0,
            ingestion_time="hour",
            ingestion_limit=20,
            ingestion_sort="top",
        ),
    )

    metrics = await runtime.run_ingestion_once(time="day", limit=5, sort="top")

    assert metrics["review_items_created"] == 1
    assert metrics["time"] == "day"
    assert sent_messages == [("12345", "digest:1:0")]
    assert metrics["pending_review_count"] == 0


@pytest.mark.asyncio
async def test_run_publish_once_uses_telegram_notification_client_when_enabled(monkeypatch) -> None:
    captured_clients: list[tuple[object, str]] = []

    class _StubThreadsClient:
        def __init__(self, *args, **kwargs) -> None:
            _ = (args, kwargs)

        async def close(self) -> None:
            return None

    class _StubTelegramClient:
        async def close(self) -> None:
            return None

    class _StubTelegramNotificationClient:
        def __init__(self, telegram_client, chat_id: str) -> None:
            captured_clients.append((telegram_client, chat_id))

    class _StubNotificationService:
        def __init__(self, client, default_recipient: str) -> None:
            self.client = client
            self.default_recipient = default_recipient

    class _StubPublishWorker:
        def __init__(self, *, notification_service, **kwargs) -> None:
            _ = kwargs
            self.notification_service = notification_service

        async def run_cycle(self, session):
            _ = session
            assert self.notification_service.default_recipient == "12345"
            assert captured_clients
            return SimpleNamespace(
                scheduled_count=1,
                processed_count=1,
                published_count=1,
                retry_scheduled_count=0,
                failed_terminal_count=0,
                cancelled_count=0,
            )

    class _SessionContext:
        async def __aenter__(self):
            return _StubSession()

        async def __aexit__(self, exc_type, exc, tb):
            _ = (exc_type, exc, tb)
            return False

    monkeypatch.setattr(runtime, "ThreadsClient", _StubThreadsClient)
    monkeypatch.setattr(runtime, "TelegramClient", lambda bot_token: _StubTelegramClient())
    monkeypatch.setattr(runtime, "TelegramNotificationClient", _StubTelegramNotificationClient)
    monkeypatch.setattr(runtime, "NotificationService", _StubNotificationService)
    monkeypatch.setattr(runtime, "PublishWorker", _StubPublishWorker)
    monkeypatch.setattr(runtime, "AsyncSessionLocal", lambda: _SessionContext())
    monkeypatch.setattr(
        runtime,
        "get_settings",
        lambda: SimpleNamespace(
            threads_api_base_url="https://threads.test",
            threads_api_token="token",
            threads_account_id="account",
            telegram_enabled=True,
            telegram_bot_token="telegram-token",
            telegram_chat_id="12345",
        ),
    )

    metrics = await runtime.run_publish_once()

    assert metrics["published_count"] == 1
    assert len(captured_clients) == 1


@pytest.mark.asyncio
async def test_run_publish_once_marks_notifications_disabled_without_telegram(monkeypatch) -> None:
    class _StubThreadsClient:
        def __init__(self, *args, **kwargs) -> None:
            _ = (args, kwargs)

        async def close(self) -> None:
            return None

    class _StubDisabledNotificationClient:
        def __init__(self, reason: str = "Telegram notifications are not configured") -> None:
            self.reason = reason

    class _StubNotificationService:
        def __init__(self, client, default_recipient: str) -> None:
            self.client = client
            self.default_recipient = default_recipient

    class _StubPublishWorker:
        def __init__(self, *, notification_service, **kwargs) -> None:
            _ = kwargs
            self.notification_service = notification_service

        async def run_cycle(self, session):
            _ = session
            assert isinstance(self.notification_service.client, _StubDisabledNotificationClient)
            assert self.notification_service.default_recipient == "telegram_disabled"
            return SimpleNamespace(
                scheduled_count=0,
                processed_count=0,
                published_count=0,
                retry_scheduled_count=0,
                failed_terminal_count=0,
                cancelled_count=0,
            )

    class _SessionContext:
        async def __aenter__(self):
            return _StubSession()

        async def __aexit__(self, exc_type, exc, tb):
            _ = (exc_type, exc, tb)
            return False

    monkeypatch.setattr(runtime, "ThreadsClient", _StubThreadsClient)
    monkeypatch.setattr(runtime, "DisabledNotificationClient", _StubDisabledNotificationClient)
    monkeypatch.setattr(runtime, "NotificationService", _StubNotificationService)
    monkeypatch.setattr(runtime, "PublishWorker", _StubPublishWorker)
    monkeypatch.setattr(runtime, "AsyncSessionLocal", lambda: _SessionContext())
    monkeypatch.setattr(
        runtime,
        "get_settings",
        lambda: SimpleNamespace(
            threads_api_base_url="https://threads.test",
            threads_api_token="token",
            threads_account_id="account",
            telegram_enabled=False,
            telegram_bot_token="",
            telegram_chat_id="",
        ),
    )

    metrics = await runtime.run_publish_once()

    assert metrics["published_count"] == 0
