import httpx
import pytest

from src.integrations.moltbook_api_client import MoltbookAPIClient


@pytest.mark.asyncio
async def test_list_posts_returns_required_contract_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["window"] == "today"
        return httpx.Response(
            status_code=200,
            json={
                "items": [
                    {
                        "source_url": "https://moltbook.com/p/1",
                        "source_post_id": "1",
                        "author_handle": "alice",
                        "content_text": "Hello Moltbook",
                        "created_at": "2026-02-24T00:00:00Z",
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

    posts, cursor = await client.list_posts(window="today", limit=10)

    assert cursor is None
    assert len(posts) == 1
    assert posts[0].source_url == "https://moltbook.com/p/1"
    assert posts[0].content_text
    assert posts[0].created_at


@pytest.mark.asyncio
async def test_list_posts_rejects_unsupported_window() -> None:
    client = MoltbookAPIClient(base_url="https://api.moltbook.test", token="token")

    with pytest.raises(ValueError, match="Unsupported window"):
        await client.list_posts(window="unknown")
