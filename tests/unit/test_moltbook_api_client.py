import httpx
import pytest

from src.integrations.moltbook_api_client import MoltbookAPIClient


@pytest.mark.asyncio
async def test_fetch_comments_returns_parsed_comments() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/posts/post-1/comments")
        assert request.url.params["sort"] == "top"
        assert request.url.params["limit"] == "5"
        return httpx.Response(
            200,
            json={
                "items": [
                    {"author_handle": "alice", "content_text": "First", "upvotes": 10},
                    {"author": {"name": "bob"}, "content": "Second", "upvotes": 4},
                ]
            },
        )

    client = MoltbookAPIClient(
        base_url="https://api.moltbook.test",
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        comments = await client.fetch_comments("post-1")
    finally:
        await client.close()

    assert len(comments) == 2
    assert comments[0].author_handle == "alice"
    assert comments[0].content_text == "First"
    assert comments[0].upvotes == 10
    assert comments[1].author_handle == "bob"
    assert comments[1].content_text == "Second"


@pytest.mark.asyncio
async def test_fetch_comments_handles_empty_response() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    client = MoltbookAPIClient(
        base_url="https://api.moltbook.test",
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        comments = await client.fetch_comments("post-2")
    finally:
        await client.close()

    assert comments == []


@pytest.mark.asyncio
async def test_fetch_comments_returns_empty_list_on_api_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    client = MoltbookAPIClient(
        base_url="https://api.moltbook.test",
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        comments = await client.fetch_comments("post-3")
    finally:
        await client.close()

    assert comments == []
