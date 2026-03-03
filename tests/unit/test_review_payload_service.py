import json

import httpx

from src.services.review_payload_service import ReviewPayloadService


def test_translate_to_chinese_uses_thinking_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/chat")
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["think"] is False
        assert "Translate the input into Traditional Chinese" in payload["messages"][0]["content"]
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": "This is translated content."}}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client)

    payload = service.build_payload(raw_content="This is source text.", risk_score=1)

    assert payload.chinese_translation_full == "This is translated content."
    assert payload.risk_tags == ["low-risk"]


def test_translate_falls_back_to_legacy_thinking_flag_when_think_is_rejected() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        payload = json.loads(request.content.decode("utf-8"))
        if call_count == 1:
            assert "think" in payload
            return httpx.Response(400, text='{"error":"unknown field \\"think\\""}')

        assert "thinking" in payload
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Fallback translated content."}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client)

    payload = service.build_payload(raw_content="Fallback translation source.", risk_score=2)

    assert call_count == 2
    assert payload.chinese_translation_full == "Fallback translated content."
    assert payload.risk_tags == ["medium-risk"]


def test_translate_strips_think_block_from_message_content() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "<think>draft chain</think>\n\nFinal translated content.",
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ReviewPayloadService(ollama_client=client)

    payload = service.build_payload(raw_content="source", risk_score=1)

    assert payload.chinese_translation_full == "Final translated content."
