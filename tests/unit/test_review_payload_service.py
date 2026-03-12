import json

import httpx
import pytest

from src.integrations.moltbook_api_client import MoltbookComment
from src.services.review_payload_service import ReviewPayloadService


@pytest.mark.asyncio
async def test_build_payload_skips_translation_when_language_is_empty() -> None:
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text="should not be called")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="")

    payload = await service.build_payload(
        raw_content="This is source text.",
        risk_score=1,
        top_comments=[MoltbookComment(author_handle="alice", content_text="Nice post", upvotes=2)],
        final_score=1.0,
        source_url="https://www.moltbook.com/posts/1",
    )

    assert call_count == 0
    assert payload.chinese_translation_full == ""
    assert payload.top_comments_snapshot[0]["content_text"] == "Nice post"
    assert payload.top_comments_translated == []
    assert payload.threads_draft == ""
    assert payload.risk_tags == ["low-risk"]


@pytest.mark.asyncio
async def test_build_payload_translates_content_and_comments_with_batch_call() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["think"] is False
        assert set(payload["format"]["required"]) == {"content", "comment_1"}
        assert "Input JSON:" in payload["messages"][0]["content"]
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": '{"content":"翻譯內容","comment_1":"翻譯留言"}'}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")

    payload = await service.build_payload(
        raw_content="Source",
        risk_score=2,
        top_comments=[MoltbookComment(author_handle="bob", content_text="Comment", upvotes=5)],
        final_score=1.0,
        source_url="https://www.moltbook.com/posts/2",
    )

    assert call_count == 1
    assert payload.chinese_translation_full == "翻譯內容"
    assert payload.top_comments_translated[0]["content_text"] == "翻譯留言"
    assert payload.risk_tags == ["medium-risk"]


@pytest.mark.asyncio
async def test_translate_batch_with_content_only_uses_content_schema() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["format"]["required"] == ["content"]
        return httpx.Response(200, json={"message": {"role": "assistant", "content": '{"content":"譯文"}'}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")

    translated_content, translated_comments = await service._translate_batch(
        "Source only",
        [],
        target_language="zh-TW",
    )

    assert translated_content == "譯文"
    assert translated_comments == []


@pytest.mark.asyncio
async def test_translate_batch_skips_empty_comment_and_preserves_empty_translation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert set(payload["format"]["required"]) == {"comment_2"}
        return httpx.Response(200, json={"message": {"role": "assistant", "content": '{"comment_2":"第二則翻譯"}'}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")

    translated_content, translated_comments = await service._translate_batch(
        "",
        [
            MoltbookComment(author_handle="a", content_text="", upvotes=1),
            MoltbookComment(author_handle="b", content_text="Second comment", upvotes=2),
        ],
        target_language="zh-TW",
    )

    assert translated_content == ""
    assert translated_comments[0]["content_text"] == ""
    assert translated_comments[1]["content_text"] == "第二則翻譯"


@pytest.mark.asyncio
async def test_translate_batch_falls_back_to_sequential_on_json_parse_error() -> None:
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "not json"}})
        return httpx.Response(200, json={"message": {"role": "assistant", "content": f"fallback-{call_count}"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")

    translated_content, translated_comments = await service._translate_batch(
        "Raw",
        [MoltbookComment(author_handle="u", content_text="Comment", upvotes=1)],
        target_language="zh-TW",
    )

    assert call_count == 3
    assert translated_content == "fallback-2"
    assert translated_comments[0]["content_text"] == "fallback-3"


@pytest.mark.asyncio
async def test_translate_batch_http_error_disables_ollama_and_returns_empty_translations() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("translation failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")

    translated_content, translated_comments = await service._translate_batch(
        "Raw",
        [MoltbookComment(author_handle="u", content_text="Comment", upvotes=1)],
        target_language="zh-TW",
    )

    assert call_count == 3
    assert translated_content == ""
    assert translated_comments[0]["content_text"] == ""
    assert service._ollama_enabled is False
    assert service._consecutive_failures == 3


@pytest.mark.asyncio
async def test_translate_http_error_single_failure_keeps_ollama_enabled() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("translation failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")

    translated = await service._translate("Raw", "zh-TW")

    assert translated == ""
    assert service._ollama_enabled is True
    assert service._consecutive_failures == 1


@pytest.mark.asyncio
async def test_translate_success_resets_consecutive_failures() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("translation failed", request=request)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "翻譯成功"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")

    assert await service._translate("Raw", "zh-TW") == ""
    assert service._consecutive_failures == 1

    assert await service._translate("Raw", "zh-TW") == "翻譯成功"
    assert service._ollama_enabled is True
    assert service._consecutive_failures == 0


@pytest.mark.asyncio
async def test_non_http_errors_do_not_increment_consecutive_failures() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant", "content": ""}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")

    translated = await service._translate("Raw", "zh-TW")

    assert translated == ""
    assert service._ollama_enabled is True
    assert service._consecutive_failures == 0


@pytest.mark.asyncio
async def test_build_payload_batch_translation_output_matches_expected_structure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"content":"主文翻譯","comment_1":"留言翻譯一","comment_2":"留言翻譯二"}',
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")
    comments = [
        MoltbookComment(author_handle="alice", content_text="First", upvotes=3),
        MoltbookComment(author_handle="bob", content_text="Second", upvotes=2),
    ]

    payload = await service.build_payload(
        raw_content="Source body",
        risk_score=1,
        top_comments=comments,
        final_score=1.0,
        source_url="https://www.moltbook.com/post/1",
    )

    assert payload.chinese_translation_full == "主文翻譯"
    assert payload.top_comments_translated == [
        {"author_handle": "alice", "content_text": "留言翻譯一", "upvotes": 3},
        {"author_handle": "bob", "content_text": "留言翻譯二", "upvotes": 2},
    ]


@pytest.mark.asyncio
async def test_generate_threads_draft_appends_source_url_and_strips_model_urls() -> None:
    captured_prompt = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_prompt
        payload = json.loads(request.content.decode("utf-8"))
        captured_prompt = payload["messages"][0]["content"]
        assert payload["think"] is True
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "<think>draft chain</think>\n\nDraft body https://example.com/extra",
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="", threads_language="en")

    payload = await service.build_payload(
        raw_content="Source post body",
        risk_score=1,
        top_comments=[MoltbookComment(author_handle="carol", content_text="Great angle", upvotes=9)],
        final_score=4.2,
        source_url="https://www.moltbook.com/posts/3",
    )

    assert "Spark curiosity and drive traffic to the original Moltbook post." in captured_prompt
    assert "Length & Density:" in captured_prompt
    assert "2 to 3 short paragraphs." in captured_prompt
    assert "sharp, opinionated takeaway" in captured_prompt
    assert "No bullet points, numbered lists, or Markdown syntax." in captured_prompt
    assert "Do not include any URLs." in captured_prompt
    assert "Top comments:" in captured_prompt
    assert "Score:" not in captured_prompt
    assert "https://example.com/extra" not in payload.threads_draft
    assert payload.threads_draft.endswith("\n\nhttps://www.moltbook.com/posts/3")


@pytest.mark.asyncio
async def test_generate_threads_draft_falls_back_when_think_is_not_supported() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        payload = json.loads(request.content.decode("utf-8"))
        if call_count == 1:
            assert payload["think"] is True
            return httpx.Response(400, text='{"error":"\\"gemma3:4b\\" does not support thinking"}')

        assert payload["think"] is False
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Thread draft body"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="", threads_language="en")

    payload = await service.build_payload(
        raw_content="content",
        risk_score=1,
        final_score=4.0,
        source_url="https://www.moltbook.com/posts/7",
    )

    assert call_count == 2
    assert payload.threads_draft == "Thread draft body\n\nhttps://www.moltbook.com/posts/7"
