import json

import httpx

from src.integrations.moltbook_api_client import MoltbookComment
from src.services.review_payload_service import ReviewPayloadService


def test_build_payload_skips_translation_when_language_is_empty() -> None:
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text="should not be called")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="")

    payload = service.build_payload(
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


def test_build_payload_translates_content_and_comments_when_language_set() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["think"] is False
        assert "Japanese" in payload["messages"][0]["content"]
        assert "Translate all sentences" in payload["messages"][0]["content"]
        assert "output must be entirely in the target language" in payload["messages"][0]["content"].lower()
        return httpx.Response(200, json={"message": {"role": "assistant", "content": f"translated-{call_count}"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="ja")

    payload = service.build_payload(
        raw_content="Source",
        risk_score=2,
        top_comments=[MoltbookComment(author_handle="bob", content_text="Comment", upvotes=5)],
        final_score=1.0,
        source_url="https://www.moltbook.com/posts/2",
    )

    assert call_count == 2
    assert payload.chinese_translation_full == "translated-1"
    assert payload.top_comments_translated[0]["content_text"] == "translated-2"
    assert payload.risk_tags == ["medium-risk"]


def test_translate_retries_without_thinking_param_when_think_field_is_rejected() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        payload = json.loads(request.content.decode("utf-8"))
        if call_count == 1:
            assert "think" in payload
            return httpx.Response(400, text='{"error":"unknown field \\"think\\""}')

        assert "thinking" not in payload
        assert "think" not in payload
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "這是回退翻譯內容。"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")

    payload = service.build_payload(raw_content="Fallback translation source.", risk_score=2, final_score=1.0)

    assert call_count == 2
    assert payload.chinese_translation_full == "這是回退翻譯內容。"
    assert payload.risk_tags == ["medium-risk"]


def test_translate_does_not_apply_language_quality_retry_check() -> None:
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Oi, agente! texto em portugues"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")

    payload = service.build_payload(raw_content="Oi, agente!", risk_score=1, final_score=1.0)

    assert call_count == 1
    assert payload.chinese_translation_full == "Oi, agente! texto em portugues"


def test_generate_threads_draft_appends_source_url_and_strips_model_urls() -> None:
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

    payload = service.build_payload(
        raw_content="Source post body",
        risk_score=1,
        top_comments=[MoltbookComment(author_handle="carol", content_text="Great angle", upvotes=9)],
        final_score=4.2,
        source_url="https://www.moltbook.com/posts/3",
    )

    assert "attract clicks, likes, and discussion" in captured_prompt
    assert "Length:" in captured_prompt
    assert "3 to 5 short paragraphs." in captured_prompt
    assert "call-to-action question" in captured_prompt
    assert "No bullet points or numbered lists." in captured_prompt
    assert "Do not include any URLs." in captured_prompt
    assert "Top comments:" in captured_prompt
    assert "Score:" not in captured_prompt
    assert "https://example.com/extra" not in payload.threads_draft
    assert payload.threads_draft.endswith("\n\nhttps://www.moltbook.com/posts/3")


def test_generate_threads_draft_returns_empty_string_on_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="", threads_language="en")

    payload = service.build_payload(
        raw_content="content",
        risk_score=1,
        final_score=4.0,
        source_url="https://www.moltbook.com/posts/4",
    )

    assert payload.threads_draft == ""


def test_generate_threads_draft_returns_empty_when_output_is_near_source_copy() -> None:
    source_text = "This is the original post body. It should not be reused as-is."

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant", "content": source_text}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="", threads_language="en")

    payload = service.build_payload(
        raw_content=source_text,
        risk_score=1,
        final_score=4.0,
        source_url="https://www.moltbook.com/posts/8",
    )

    assert payload.threads_draft == ""


def test_generate_threads_draft_falls_back_when_think_is_not_supported() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        payload = json.loads(request.content.decode("utf-8"))
        if call_count == 1:
            assert payload["think"] is True
            return httpx.Response(400, text='{"error":"\\"gemma3:4b\\" does not support thinking"}')

        assert "thinking" not in payload
        assert payload["think"] is False
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Thread draft body"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="", threads_language="en")

    payload = service.build_payload(
        raw_content="content",
        risk_score=1,
        final_score=4.0,
        source_url="https://www.moltbook.com/posts/7",
    )

    assert call_count == 2
    assert payload.threads_draft == "Thread draft body\n\nhttps://www.moltbook.com/posts/7"


def test_translate_returns_empty_string_on_failure_instead_of_source() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("translation failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="zh-TW")

    payload = service.build_payload(
        raw_content="source content",
        risk_score=1,
        final_score=1.0,
        source_url="https://www.moltbook.com/posts/6",
    )

    assert payload.chinese_translation_full == ""


def test_generate_threads_draft_skips_when_score_below_threshold() -> None:
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text="should not be called")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client, translation_language="", threads_language="en")

    payload = service.build_payload(
        raw_content="content",
        risk_score=1,
        final_score=2.0,
        source_url="https://www.moltbook.com/posts/5",
    )

    assert call_count == 0
    assert payload.threads_draft == ""
