from __future__ import annotations

import httpx


class ThreadsClient:
    def __init__(self, base_url: str, token: str, account_id: str, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._account_id = account_id
        self._client = client or httpx.AsyncClient(timeout=20)
        self._owns_client = client is None

    async def publish_post(self, *, text: str, source_url: str) -> str:
        response = await self._client.post(
            f"{self._base_url}/publish",
            headers={"Authorization": f"Bearer {self._token}"},
            json={
                "accountId": self._account_id,
                "text": text,
                "sourceUrl": source_url,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return payload["postId"]

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
