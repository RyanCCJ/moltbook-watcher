from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

_SUPPORTED_WINDOWS = {"all_time", "year", "month", "week", "today", "past_hour"}
_SUPPORTED_SORTS = {"hot", "new", "top", "rising"}
_MAX_SCAN_PAGES = 3
_MAX_SCAN_POSTS = 60
_MIN_SCAN_POSTS = 12
_PAGE_LIMIT_CAP = 25


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
        sort: str = "top",
    ) -> tuple[list[MoltbookPost], str | None]:
        if window not in _SUPPORTED_WINDOWS:
            raise ValueError(f"Unsupported window: {window}")
        if sort not in _SUPPORTED_SORTS:
            raise ValueError(f"Unsupported sort: {sort}")

        target_limit = max(1, limit)
        scan_budget = min(_MAX_SCAN_POSTS, max(_MIN_SCAN_POSTS, target_limit * 3))
        cursor_token = cursor
        scanned_count = 0
        collected: list[MoltbookPost] = []

        for _ in range(_MAX_SCAN_PAGES):
            remaining_budget = scan_budget - scanned_count
            if remaining_budget <= 0:
                break

            page_limit = min(_PAGE_LIMIT_CAP, remaining_budget)
            response = await self._client.get(
                f"{self._base_url}/posts",
                params={"sort": sort, "cursor": cursor_token, "limit": page_limit},
                headers={"Authorization": f"Bearer {self._token}"},
            )
            response.raise_for_status()
            payload = response.json()

            raw_items = payload.get("items")
            if raw_items is None:
                raw_items = payload.get("posts", [])
            if not raw_items:
                return collected[:target_limit], payload.get("next_cursor")

            parsed_items = [self._parse_item(item) for item in raw_items]
            scanned_count += len(parsed_items)
            collected.extend(post for post in parsed_items if self._matches_window(post.created_at, window))
            if len(collected) >= target_limit:
                return collected[:target_limit], payload.get("next_cursor")

            cursor_token = payload.get("next_cursor")
            if cursor_token is None:
                return collected[:target_limit], None

        return collected[:target_limit], cursor_token

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

    @staticmethod
    def _matches_window(created_at: datetime, window: str) -> bool:
        if window == "all_time":
            return True

        now = datetime.now(tz=UTC)
        if window == "past_hour":
            cutoff = now - timedelta(hours=1)
        elif window == "today":
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif window == "week":
            cutoff = now - timedelta(days=7)
        elif window == "month":
            cutoff = now - timedelta(days=30)
        elif window == "year":
            cutoff = now - timedelta(days=365)
        else:  # pragma: no cover - protected by window validation in list_posts
            return False
        return created_at >= cutoff
