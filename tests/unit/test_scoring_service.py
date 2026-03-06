import json

import httpx
import pytest

from src.integrations.moltbook_api_client import MoltbookComment
from src.services.scoring_service import ScoreVector, ScoringService


def test_final_score_applies_risk_penalty() -> None:
    service = ScoringService(risk_penalty_weight=0.2)
    low_risk = ScoreVector(
        novelty=4.0,
        depth=4.0,
        tension=4.0,
        reflective_impact=4.0,
        engagement=4.0,
        risk=1,
    )
    high_risk = ScoreVector(
        novelty=4.0,
        depth=4.0,
        tension=4.0,
        reflective_impact=4.0,
        engagement=4.0,
        risk=5,
    )

    low = service.compute_scores(low_risk)
    high = service.compute_scores(high_risk)

    assert low.final_score > high.final_score
    assert low.final_score == 3.8
    assert high.final_score == 3.0


def test_final_score_is_clamped_between_zero_and_five() -> None:
    service = ScoringService(risk_penalty_weight=0.5)
    vector = ScoreVector(
        novelty=0.2,
        depth=0.1,
        tension=0.1,
        reflective_impact=0.1,
        engagement=0.1,
        risk=5,
    )
    result = service.compute_scores(vector)

    assert result.content_score == 0.12
    assert result.final_score == 0.0


@pytest.mark.asyncio
async def test_score_candidate_prefers_ollama_when_available() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/chat")
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["think"] is True
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"novelty":4.5,"depth":4.0,"tension":3.5,"reflective_impact":4.2,"engagement":3.8,"risk":1}',
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ScoringService(ollama_client=client)

    result = await service.score_candidate("test content", {"likes": 1})

    assert result.novelty == 4.5
    assert result.depth == 4.0
    assert result.tension == 3.5
    assert result.reflective_impact == 4.2
    assert result.engagement == 3.8
    assert result.risk == 1
    assert result.content_score == 4.0
    assert result.final_score == 3.8


@pytest.mark.asyncio
async def test_score_candidate_retries_with_think_false_when_think_is_rejected() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        payload = json.loads(request.content.decode("utf-8"))

        if call_count == 1:
            assert "think" in payload
            return httpx.Response(400, text='{"error":"unknown field \\"think\\""}')

        assert "thinking" not in payload
        assert payload["think"] is False
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"novelty":4.2,"depth":3.9,"tension":3.6,"reflective_impact":4.0,"engagement":3.7,"risk":1}',
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ScoringService(ollama_client=client)

    result = await service.score_candidate("fallback content", {"likes": 2})

    assert call_count == 2
    assert result.novelty == 4.2
    assert result.final_score == 3.68


@pytest.mark.asyncio
async def test_score_candidate_retries_with_json_mode_when_first_response_is_not_json() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        payload = json.loads(request.content.decode("utf-8"))

        if call_count == 1:
            assert payload["format"]["type"] == "object"
            return httpx.Response(
                200, json={"message": {"role": "assistant", "content": "novelty=4, depth=4, risk=1"}}
            )

        assert payload["format"] == "json"
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"novelty":4.0,"depth":3.5,"tension":3.0,"reflective_impact":4.0,"engagement":3.5,"risk":1}',
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ScoringService(ollama_client=client)

    result = await service.score_candidate("retry content", {"likes": 3})

    assert call_count == 2
    assert result.novelty == 4.0
    assert result.final_score == 3.4


@pytest.mark.asyncio
async def test_score_candidate_does_not_disable_ollama_after_invalid_json() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "still-not-json"}})

        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"novelty":4.1,"depth":4.0,"tension":3.8,"reflective_impact":4.2,"engagement":3.9,"risk":1}',
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ScoringService(ollama_client=client)

    first = await service.score_candidate("first try", {"likes": 1})
    second = await service.score_candidate("second try", {"likes": 1})

    assert call_count == 3
    assert first.score_version == "v1"
    assert second.novelty == 4.1


@pytest.mark.asyncio
async def test_score_candidate_falls_back_to_heuristic_and_disables_after_ollama_error() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("connection failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ScoringService(ollama_client=client)

    first = await service.score_candidate("safe test content", {"likes": 1})
    second = await service.score_candidate("safe test content", {"likes": 1})

    assert call_count == 1
    assert first.score_version == "v1"
    assert second.score_version == "v1"
    assert first.risk == 1
    assert second.risk == 1


@pytest.mark.asyncio
async def test_score_candidate_includes_top_comments_in_prompt() -> None:
    captured_prompt = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_prompt
        payload = json.loads(request.content.decode("utf-8"))
        captured_prompt = payload["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"novelty":4.0,"depth":4.0,"tension":4.0,"reflective_impact":4.0,"engagement":4.0,"risk":1}',
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ScoringService(ollama_client=client)

    await service.score_candidate(
        "Prompt with comments",
        {"likes": 2, "comments": 1},
        top_comments=[MoltbookComment(author_handle="alice", content_text="Great insight", upvotes=12)],
    )

    assert "Top comments:" in captured_prompt
    assert "@alice: Great insight" in captured_prompt


@pytest.mark.asyncio
async def test_score_candidate_prompt_marks_no_comments_when_absent() -> None:
    captured_prompt = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_prompt
        payload = json.loads(request.content.decode("utf-8"))
        captured_prompt = payload["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"novelty":3.0,"depth":3.0,"tension":3.0,"reflective_impact":3.0,"engagement":3.0,"risk":1}',
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ScoringService(ollama_client=client)

    await service.score_candidate("Prompt without comments", {"likes": 1}, top_comments=[])

    assert "Top comments:" in captured_prompt
    assert "(none)" in captured_prompt
