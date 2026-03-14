from types import SimpleNamespace

import pytest

from src.api import app as app_module


class _StubTelegramClient:
    def __init__(self, bot_token: str) -> None:
        self.bot_token = bot_token
        self.set_webhook_calls: list[tuple[str, str]] = []
        self.closed = False

    async def set_webhook(self, url: str, secret_token: str) -> dict:
        self.set_webhook_calls.append((url, secret_token))
        return {"ok": True}

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_create_app_registers_and_closes_telegram_client(monkeypatch) -> None:
    stub_clients: list[_StubTelegramClient] = []

    def build_client(bot_token: str) -> _StubTelegramClient:
        client = _StubTelegramClient(bot_token)
        stub_clients.append(client)
        return client

    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: SimpleNamespace(
            log_level="INFO",
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            telegram_enabled=True,
            telegram_bot_token="bot-token",
            telegram_chat_id="12345",
            telegram_webhook_url="https://example.com/telegram/webhook",
            publish_mode="manual-approval",
            ingestion_time="hour",
            ingestion_sort="top",
            ingestion_limit=20,
            review_min_score=3.5,
            auto_publish_min_score=4.0,
        ),
    )
    monkeypatch.setattr(app_module, "TelegramClient", build_client)

    app = app_module.create_app()

    assert any(route.path == "/telegram/webhook" for route in app.routes)

    await app.router.startup()

    assert len(stub_clients) == 1
    assert app.state.telegram_webhook_registered is True
    assert app.state.telegram_service is not None
    assert stub_clients[0].set_webhook_calls

    await app.router.shutdown()

    assert stub_clients[0].closed is True
