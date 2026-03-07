from __future__ import annotations

from typing import Any

import httpx

from src.services.logging_service import get_logger

logger = get_logger(__name__)


class TelegramClient:
    def __init__(
        self,
        bot_token: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._client = client or httpx.AsyncClient(base_url=f"https://api.telegram.org/bot{bot_token}/")
        self._owns_client = client is None

    async def set_webhook(self, url: str, secret_token: str) -> dict[str, Any]:
        return await self._post("setWebhook", url=url, secret_token=secret_token)

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._post("sendMessage", **payload)

    async def edit_message_text(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._post("editMessageText", **payload)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text is not None:
            payload["text"] = text
        return await self._post("answerCallbackQuery", **payload)

    async def delete_webhook(self) -> dict[str, Any]:
        return await self._post("deleteWebhook")

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _post(self, method_name: str, **payload: Any) -> dict[str, Any]:
        response = await self._client.post(method_name, json=payload)
        if response.status_code < 200 or response.status_code >= 300:
            logger.error(
                "telegram_api_call_failed",
                method_name=method_name,
                status_code=response.status_code,
                response_body=response.text,
            )
            raise RuntimeError(f"Telegram API {method_name} failed with status {response.status_code}")
        return response.json()
