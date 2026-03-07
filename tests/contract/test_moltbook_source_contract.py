from datetime import UTC, datetime

import httpx
import pytest

from src.integrations.moltbook_api_client import MoltbookAPIClient


@pytest.mark.asyncio
async def test_list_posts_returns_required_contract_fields() -> None:
    now = datetime.now(tz=UTC)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["sort"] == "top"
        assert request.url.params["time"] == "day"
        assert int(request.url.params["limit"]) == 10
        return httpx.Response(
            status_code=200,
            json={
                "items": [
                    {
                        "source_url": "https://moltbook.com/p/1",
                        "source_post_id": "1",
                        "author_handle": "alice",
                        "content_text": "Hello Moltbook",
                        "created_at": now.isoformat().replace("+00:00", "Z"),
                        "engagement_summary": {"likes": 3},
                    }
                ],
                "next_cursor": None,
            },
        )

    transport = httpx.MockTransport(handler)
    client = MoltbookAPIClient(
        base_url="https://api.moltbook.test",
        token="token",
        client=httpx.AsyncClient(transport=transport),
    )

    posts, cursor = await client.list_posts(time="day", limit=10)

    assert cursor is None
    assert len(posts) == 1
    assert posts[0].source_url == "https://moltbook.com/p/1"
    assert posts[0].content_text
    assert posts[0].created_at


@pytest.mark.asyncio
async def test_list_posts_rejects_unsupported_time() -> None:
    client = MoltbookAPIClient(base_url="https://api.moltbook.test", token="token")

    with pytest.raises(ValueError, match="Unsupported time"):
        await client.list_posts(time="unknown")


@pytest.mark.asyncio
async def test_list_posts_rejects_unsupported_sort() -> None:
    client = MoltbookAPIClient(base_url="https://api.moltbook.test", token="token")

    with pytest.raises(ValueError, match="Unsupported sort"):
        await client.list_posts(time="day", sort="controversial")


@pytest.mark.asyncio
async def test_list_posts_normalizes_legacy_post_url_fallback_to_canonical_route() -> None:
    now = datetime.now(tz=UTC)

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "items": [
                    {
                        "id": "abc123",
                        "author_handle": "alice",
                        "content_text": "Hello Moltbook",
                        "created_at": now.isoformat().replace("+00:00", "Z"),
                        "engagement_summary": {"likes": 3},
                    }
                ],
                "next_cursor": None,
            },
        )

    transport = httpx.MockTransport(handler)
    client = MoltbookAPIClient(
        base_url="https://api.moltbook.test",
        token="token",
        client=httpx.AsyncClient(transport=transport),
    )

    posts, _ = await client.list_posts(time="day", limit=1)

    assert len(posts) == 1
    assert posts[0].source_url == "https://www.moltbook.com/post/abc123"
