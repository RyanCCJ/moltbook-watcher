import logging

import pytest

from src.integrations.telegram_client import TelegramClient


class _Response:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, responses: list[_Response] | None = None) -> None:
        self._responses = responses or [_Response(200, {"ok": True, "result": {"message_id": 1}})]
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    async def post(self, method_name: str, json: dict) -> _Response:
        self.calls.append((method_name, json))
        return self._responses.pop(0)

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_set_webhook_posts_expected_payload() -> None:
    client = _FakeAsyncClient()
    telegram = TelegramClient("bot-token", client=client)

    result = await telegram.set_webhook("https://example.com/telegram/webhook", "secret-token")

    assert result["ok"] is True
    assert client.calls == [
        (
            "setWebhook",
            {
                "url": "https://example.com/telegram/webhook",
                "secret_token": "secret-token",
            },
        )
    ]


@pytest.mark.asyncio
async def test_send_message_uses_html_parse_mode_and_reply_markup() -> None:
    client = _FakeAsyncClient()
    telegram = TelegramClient("bot-token", client=client)
    keyboard = {"inline_keyboard": [[{"text": "Approve", "callback_data": "approve:1"}]]}

    await telegram.send_message("12345", "<b>hello</b>", reply_markup=keyboard)

    assert client.calls == [
        (
            "sendMessage",
            {
                "chat_id": "12345",
                "text": "<b>hello</b>",
                "parse_mode": "HTML",
                "reply_markup": keyboard,
            },
        )
    ]


@pytest.mark.asyncio
async def test_edit_message_text_posts_expected_payload() -> None:
    client = _FakeAsyncClient()
    telegram = TelegramClient("bot-token", client=client)

    await telegram.edit_message_text("12345", 99, "updated")

    assert client.calls == [
        (
            "editMessageText",
            {
                "chat_id": "12345",
                "message_id": 99,
                "text": "updated",
                "parse_mode": "HTML",
            },
        )
    ]


@pytest.mark.asyncio
async def test_answer_callback_query_posts_optional_text() -> None:
    client = _FakeAsyncClient()
    telegram = TelegramClient("bot-token", client=client)

    await telegram.answer_callback_query("callback-id", text="done")

    assert client.calls == [
        (
            "answerCallbackQuery",
            {
                "callback_query_id": "callback-id",
                "text": "done",
            },
        )
    ]


@pytest.mark.asyncio
async def test_delete_webhook_posts_empty_payload() -> None:
    client = _FakeAsyncClient()
    telegram = TelegramClient("bot-token", client=client)

    await telegram.delete_webhook()

    assert client.calls == [("deleteWebhook", {})]


@pytest.mark.asyncio
async def test_close_closes_owned_client(monkeypatch) -> None:
    fake_client = _FakeAsyncClient()

    class _Factory:
        def __call__(self, *args, **kwargs):
            _ = (args, kwargs)
            return fake_client

    monkeypatch.setattr("src.integrations.telegram_client.httpx.AsyncClient", _Factory())
    telegram = TelegramClient("bot-token")

    await telegram.close()

    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_post_logs_and_raises_on_non_2xx(caplog) -> None:
    caplog.set_level(logging.ERROR)
    client = _FakeAsyncClient(
        responses=[_Response(500, {"ok": False}, text='{"ok":false,"description":"boom"}')]
    )
    telegram = TelegramClient("bot-token", client=client)

    with pytest.raises(RuntimeError, match="Telegram API sendMessage failed with status 500"):
        await telegram.send_message("12345", "hello")

    assert "telegram_api_call_failed" in caplog.text
    assert '"status_code": 500' in caplog.text
    assert "boom" in caplog.text
