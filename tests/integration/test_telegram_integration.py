from types import SimpleNamespace

import httpx
import pytest

from src.api import app as app_module
from src.workers import runtime, scheduler
from tests.contract.test_telegram_routes_contract import _build_app_with_telegram, _webhook_headers


@pytest.mark.asyncio
async def test_full_telegram_approve_flow() -> None:
    app, async_session, telegram_client, review_item_id = await _build_app_with_telegram()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={
                "callback_query": {
                    "id": "approve-flow",
                    "data": f"approve:{review_item_id}",
                    "message": {
                        "message_id": 501,
                        "text": "<b>Original</b>",
                        "chat": {"id": 12345},
                    },
                }
            },
        )

    assert response.status_code == 200
    assert telegram_client.answered_callbacks == [("approve-flow", "Approved")]
    assert "<b>Decision:</b> approved" in telegram_client.edited_messages[0][2]


@pytest.mark.asyncio
async def test_full_telegram_reject_comment_flow() -> None:
    app, _, telegram_client, review_item_id = await _build_app_with_telegram()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={
                "callback_query": {
                    "id": "comment-flow",
                    "data": f"comment:{review_item_id}",
                    "message": {
                        "message_id": 502,
                        "text": "<b>Original</b>",
                        "chat": {"id": 12345},
                    },
                }
            },
        )
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"message_id": 503, "chat": {"id": 12345}, "text": "Reject reason"}},
        )

    assert response.status_code == 200
    assert telegram_client.sent_messages[0][1] == "Please type your rejection comment:"
    assert "Reject reason" in telegram_client.edited_messages[0][2]


@pytest.mark.asyncio
async def test_full_telegram_edit_draft_flow() -> None:
    app, _, telegram_client, review_item_id = await _build_app_with_telegram()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={
                "callback_query": {
                    "id": "edit-flow",
                    "data": f"edit:{review_item_id}",
                    "message": {
                        "message_id": 504,
                        "text": "<b>Original</b>",
                        "chat": {"id": 12345},
                    },
                }
            },
        )
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"message_id": 505, "chat": {"id": 12345}, "text": "Edited draft"}},
        )

    assert response.status_code == 200
    assert telegram_client.sent_messages[0][1] == "Send me the new draft text:"
    assert telegram_client.sent_messages[-1][1] == "Draft updated."


@pytest.mark.asyncio
async def test_telegram_ingest_command_sends_follow_up(monkeypatch) -> None:
    app, _, telegram_client, _ = await _build_app_with_telegram()
    created_coroutines: list = []

    async def fake_ingestion(*, time: str = "hour", sort: str = "top", limit: int = 100) -> dict[str, int | str]:
        assert (time, sort, limit) == ("hour", "top", 100)
        return {
            "time": time,
            "sort": sort,
            "limit": limit,
            "fetched_count": 3,
            "persisted_count": 2,
            "filtered_duplicate_count": 1,
            "review_items_created": 1,
        }

    monkeypatch.setattr("src.api.telegram_routes.run_ingestion_once", fake_ingestion)
    monkeypatch.setattr("src.api.telegram_routes._schedule_background_task", lambda coro: created_coroutines.append(coro))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/ingest"}},
        )

    for coroutine in created_coroutines:
        await coroutine

    assert response.status_code == 200
    assert "Ingestion started…" in telegram_client.sent_messages[0][1]
    assert "Time: hour" in telegram_client.sent_messages[0][1]
    assert "Ingestion finished." in telegram_client.sent_messages[1][1]
    assert "Time: hour" in telegram_client.sent_messages[1][1]


@pytest.mark.asyncio
async def test_telegram_ingest_command_accepts_any_order_arguments(monkeypatch) -> None:
    app, _, telegram_client, _ = await _build_app_with_telegram()
    created_coroutines: list = []

    async def fake_ingestion(*, time: str = "hour", sort: str = "top", limit: int = 100) -> dict[str, int | str]:
        assert (time, sort, limit) == ("month", "new", 20)
        return {
            "time": time,
            "sort": sort,
            "limit": limit,
            "fetched_count": 4,
            "persisted_count": 3,
            "filtered_duplicate_count": 1,
            "review_items_created": 2,
        }

    monkeypatch.setattr("src.api.telegram_routes.run_ingestion_once", fake_ingestion)
    monkeypatch.setattr("src.api.telegram_routes._schedule_background_task", lambda coro: created_coroutines.append(coro))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/ingest 20 new month"}},
        )

    for coroutine in created_coroutines:
        await coroutine

    assert response.status_code == 200
    assert "Time: month" in telegram_client.sent_messages[0][1]
    assert "Sort: new" in telegram_client.sent_messages[0][1]
    assert "Limit: 20" in telegram_client.sent_messages[0][1]
    assert "Time: month" in telegram_client.sent_messages[1][1]


@pytest.mark.asyncio
async def test_telegram_ingest_command_rejects_invalid_argument(monkeypatch) -> None:
    app, _, telegram_client, _ = await _build_app_with_telegram()
    scheduled_coroutines: list = []

    monkeypatch.setattr("src.api.telegram_routes._schedule_background_task", lambda coro: scheduled_coroutines.append(coro))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/telegram/webhook",
            headers=_webhook_headers(),
            json={"message": {"chat": {"id": 12345}, "text": "/ingest banana"}},
        )

    assert response.status_code == 200
    assert "Usage: /ingest [time] [sort] [limit]." in telegram_client.sent_messages[0][1]
    assert scheduled_coroutines == []


@pytest.mark.asyncio
async def test_telegram_features_disabled_when_token_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: SimpleNamespace(
            log_level="INFO",
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            telegram_enabled=False,
            telegram_bot_token="",
            telegram_chat_id="",
            telegram_webhook_url="",
        ),
    )
    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(
            ingestion_interval_minutes=60,
            publish_poll_minutes=5,
            telegram_enabled=False,
            telegram_chat_id="",
            telegram_daily_summary_hour=22,
            telegram_daily_summary_timezone="UTC",
        ),
    )

    app = app_module.create_app()
    built_scheduler = scheduler.build_scheduler()

    assert all(route.path != "/telegram/webhook" for route in app.routes)
    assert len(built_scheduler.get_jobs()) == 2

    class _DisabledTelegramClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("Telegram client should not be constructed when disabled")

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
        def __init__(self, *args, **kwargs) -> None:
            _ = (args, kwargs)

        async def run_cycle(self, session):
            _ = session
            return SimpleNamespace(
                scheduled_count=0,
                processed_count=0,
                published_count=0,
                retry_scheduled_count=0,
                failed_terminal_count=0,
                cancelled_count=0,
            )

    class _StubSession:
        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    class _StubSessionContext:
        async def __aenter__(self):
            return _StubSession()

        async def __aexit__(self, exc_type, exc, tb):
            _ = (exc_type, exc, tb)
            return False

    monkeypatch.setattr(runtime, "TelegramClient", _DisabledTelegramClient)
    monkeypatch.setattr(runtime, "ThreadsClient", _StubThreadsClient)
    monkeypatch.setattr(runtime, "DisabledNotificationClient", _StubDisabledNotificationClient)
    monkeypatch.setattr(runtime, "NotificationService", _StubNotificationService)
    monkeypatch.setattr(runtime, "PublishWorker", _StubPublishWorker)
    monkeypatch.setattr(runtime, "AsyncSessionLocal", lambda: _StubSessionContext())
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
