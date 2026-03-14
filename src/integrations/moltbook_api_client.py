from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from src.services.logging_service import get_logger

_SUPPORTED_TIMES = {"hour", "day", "week", "month", "all"}
_SUPPORTED_SORTS = {"hot", "new", "top", "rising"}
_LEGACY_POST_URL_PREFIX = "https://www.moltbook.com/posts/"
_CANONICAL_POST_URL_PREFIX = "https://www.moltbook.com/post/"

logger = get_logger(__name__)


@dataclass(slots=True)
class MoltbookComment:
    author_handle: str | None
    content_text: str
    upvotes: int


@dataclass(slots=True)
class MoltbookPost:
    source_url: str
    source_post_id: str | None
    author_handle: str | None
    content_text: str
    created_at: datetime
    engagement_summary: dict | None
    upvotes: int = 0
    top_comments: list[MoltbookComment] = field(default_factory=list)


class MoltbookAPIClient:
    def __init__(self, base_url: str, token: str, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client = client or httpx.AsyncClient(base_url=self._base_url, timeout=20)
        self._owns_client = client is None

    async def list_posts(
        self,
        time: str,
        cursor: str | None = None,
        limit: int = 100,
        sort: str = "top",
    ) -> tuple[list[MoltbookPost], str | None]:
        if time not in _SUPPORTED_TIMES:
            raise ValueError(f"Unsupported time: {time}")
        if sort not in _SUPPORTED_SORTS:
            raise ValueError(f"Unsupported sort: {sort}")

        response = await self._client.get(
            f"{self._base_url}/posts",
            params={"sort": sort, "time": time, "cursor": cursor, "limit": max(1, limit)},
            headers={"Authorization": f"Bearer {self._token}"},
        )
        response.raise_for_status()
        payload = response.json()

        raw_items = payload.get("items")
        if raw_items is None:
            raw_items = payload.get("posts", [])
        if not raw_items:
            return [], payload.get("next_cursor")

        parsed_items = [self._parse_item(item) for item in raw_items]
        return parsed_items[: max(1, limit)], payload.get("next_cursor")

    async def fetch_comments(
        self,
        post_id: str,
        limit: int = 5,
        sort: str = "top",
    ) -> list[MoltbookComment]:
        if not post_id:
            return []

        params = {
            "sort": sort,
            "limit": max(1, limit),
        }
        try:
            response = await self._client.get(
                f"{self._base_url}/posts/{post_id}/comments",
                params=params,
                headers={"Authorization": f"Bearer {self._token}"},
            )
            response.raise_for_status()
            payload = response.json()

            raw_items = payload.get("items")
            if raw_items is None:
                raw_items = payload.get("comments", [])
            if not isinstance(raw_items, list):
                return []

            parsed_comments: list[MoltbookComment] = []
            for item in raw_items[: max(1, limit)]:
                try:
                    parsed_comments.append(self._parse_comment(item))
                except ValueError:
                    continue
            return parsed_comments
        except Exception as error:  # pragma: no cover - non-fatal path
            logger.warning("moltbook_fetch_comments_failed", post_id=post_id, reason=str(error))
            return []

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
            source_url = f"{_CANONICAL_POST_URL_PREFIX}{source_post_id}"
        if source_url:
            source_url = MoltbookAPIClient._normalize_source_url(source_url)
        if not source_url:
            raise ValueError("Missing source_url and post id in Moltbook post payload")

        content_text = item.get("content_text") or item.get("content") or ""
        if not content_text:
            raise ValueError("Missing content text in Moltbook post payload")

        author_handle = item.get("author_handle")
        if author_handle is None and isinstance(item.get("author"), dict):
            author_handle = item["author"].get("name")

        try:
            upvotes = max(0, int(item.get("upvotes", 0)))
        except (TypeError, ValueError):
            upvotes = 0

        return MoltbookPost(
            source_url=source_url,
            source_post_id=source_post_id,
            author_handle=author_handle,
            content_text=content_text,
            created_at=parsed_dt,
            engagement_summary=item.get("engagement_summary"),
            upvotes=upvotes,
        )

    @staticmethod
    def _parse_comment(item: dict) -> MoltbookComment:
        author_handle = item.get("author_handle")
        if author_handle is None and isinstance(item.get("author"), dict):
            author_handle = item["author"].get("handle") or item["author"].get("name")

        content_text = item.get("content_text") or item.get("content") or item.get("body") or ""
        content_text = str(content_text).strip()
        if not content_text:
            raise ValueError("missing_comment_content")

        upvotes_raw = item.get("upvotes")
        if upvotes_raw is None and isinstance(item.get("engagement_summary"), dict):
            upvotes_raw = item["engagement_summary"].get("upvotes")
        if upvotes_raw is None:
            upvotes_raw = 0

        return MoltbookComment(
            author_handle=author_handle,
            content_text=content_text,
            upvotes=max(0, int(upvotes_raw)),
        )

    @staticmethod
    def _normalize_source_url(source_url: str) -> str:
        if source_url.startswith(_LEGACY_POST_URL_PREFIX):
            return source_url.replace(_LEGACY_POST_URL_PREFIX, _CANONICAL_POST_URL_PREFIX, 1)
        return source_url
