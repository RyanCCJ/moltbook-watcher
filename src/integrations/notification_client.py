from __future__ import annotations

from abc import ABC, abstractmethod
from html import escape

from src.integrations.telegram_client import TelegramClient


class NotificationClient(ABC):
    @abstractmethod
    async def send_notification(self, subject: str, body: str) -> None:
        raise NotImplementedError


class TelegramNotificationClient(NotificationClient):
    def __init__(self, telegram_client: TelegramClient, chat_id: str) -> None:
        self._telegram_client = telegram_client
        self._chat_id = chat_id

    async def send_notification(self, subject: str, body: str) -> None:
        message = f"<b>{escape(subject)}</b>\n\n{escape(body)}"
        await self._telegram_client.send_message(self._chat_id, message)


class DisabledNotificationClient(NotificationClient):
    def __init__(self, reason: str = "Telegram notifications are not configured") -> None:
        self._reason = reason

    async def send_notification(self, subject: str, body: str) -> None:
        _ = (subject, body)
        raise RuntimeError(self._reason)
