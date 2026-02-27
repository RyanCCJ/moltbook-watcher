from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

_SUPPORTED_WINDOWS = {"all_time", "year", "month", "week", "today", "past_hour"}


@dataclass(slots=True)
class MoltbookPost:
    source_url: str
    source_post_id: str | None
    author_handle: str | None
    content_text: str
    created_at: datetime
    engagement_summary: dict | None


class MoltbookAPIClient:
    def __init__(self, base_url: str, token: str, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client = client or httpx.AsyncClient(base_url=self._base_url, timeout=20)
        self._owns_client = client is None

    async def list_posts(
        self,
        window: str,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[MoltbookPost], str | None]:
        if window not in _SUPPORTED_WINDOWS:
            raise ValueError(f"Unsupported window: {window}")

        response = await self._client.get(
            f"{self._base_url}/posts",
            params={"window": window, "cursor": cursor, "limit": limit},
            headers={"Authorization": f"Bearer {self._token}"},
        )
        response.raise_for_status()
        payload = response.json()

        raw_items = payload.get("items")
        if raw_items is None:
            raw_items = payload.get("posts", [])

        items = [self._parse_item(item) for item in raw_items]
        return items, payload.get("next_cursor")

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _parse_item(item: dict) -> MoltbookPost:
        created_at = item.get("created_at") or item.get("createdAt")
        if not created_at:
            raise ValueError("Missing created_at in Moltbook post payload")
        parsed_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(UTC)

        source_post_id = item.get("source_post_id") or item.get("id")
        source_url = item.get("source_url")
        if not source_url and source_post_id:
            source_url = f"https://www.moltbook.com/posts/{source_post_id}"
        if not source_url:
            raise ValueError("Missing source_url and post id in Moltbook post payload")

        content_text = item.get("content_text") or item.get("content") or ""
        if not content_text:
            raise ValueError("Missing content text in Moltbook post payload")

        author_handle = item.get("author_handle")
        if author_handle is None and isinstance(item.get("author"), dict):
            author_handle = item["author"].get("name")

        return MoltbookPost(
            source_url=source_url,
            source_post_id=source_post_id,
            author_handle=author_handle,
            content_text=content_text,
            created_at=parsed_dt,
            engagement_summary=item.get("engagement_summary"),
        )
