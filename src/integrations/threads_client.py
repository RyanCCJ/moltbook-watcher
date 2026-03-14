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
        create_url = f"{self._base_url}/v1.0/{self._account_id}/threads"
        create_response = await self._client.post(
            create_url,
            params={
                "media_type": "TEXT",
                "text": text,
                "access_token": self._token,
            },
        )
        try:
            create_response.raise_for_status()
        except httpx.HTTPStatusError as e:
            error_msg = e.response.text
            raise RuntimeError(f"Failed to create Threads media container: {error_msg}") from e
        
        creation_id = create_response.json()["id"]

        publish_url = f"{self._base_url}/v1.0/{self._account_id}/threads_publish"
        publish_response = await self._client.post(
            publish_url,
            params={
                "creation_id": creation_id,
                "access_token": self._token,
            },
        )
        try:
            publish_response.raise_for_status()
        except httpx.HTTPStatusError as e:
            error_msg = e.response.text
            raise RuntimeError(f"Failed to publish Threads container: {error_msg}") from e
            
        return publish_response.json()["id"]

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
