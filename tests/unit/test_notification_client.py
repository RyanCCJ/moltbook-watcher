import pytest

from src.integrations.notification_client import TelegramNotificationClient


class _StubTelegramClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def send_message(self, chat_id: str, text: str) -> None:
        self.calls.append((chat_id, text))


@pytest.mark.asyncio
async def test_telegram_notification_client_sends_subject_and_body() -> None:
    telegram_client = _StubTelegramClient()
    client = TelegramNotificationClient(telegram_client=telegram_client, chat_id="chat-123")

    await client.send_notification("Publish failed", "Job 42 exploded <hard>")

    assert telegram_client.calls == [
        (
            "chat-123",
            "<b>Publish failed</b>\n\nJob 42 exploded &lt;hard&gt;",
        )
    ]
