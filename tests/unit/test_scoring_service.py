import httpx

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


def test_score_candidate_prefers_ollama_when_available() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/generate")
        return httpx.Response(
            200,
            json={
                "response": '{"novelty":4.5,"depth":4.0,"tension":3.5,"reflective_impact":4.2,"engagement":3.8,"risk":1}'
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ScoringService(ollama_client=client)

    result = service.score_candidate("test content", {"likes": 1})

    assert result.novelty == 4.5
    assert result.depth == 4.0
    assert result.tension == 3.5
    assert result.reflective_impact == 4.2
    assert result.engagement == 3.8
    assert result.risk == 1
    assert result.content_score == 4.0
    assert result.final_score == 3.8


def test_score_candidate_falls_back_to_heuristic_and_disables_after_ollama_error() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("connection failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ScoringService(ollama_client=client)

    first = service.score_candidate("safe test content", {"likes": 1})
    second = service.score_candidate("safe test content", {"likes": 1})

    assert call_count == 1
    assert first.score_version == "v1"
    assert second.score_version == "v1"
    assert first.risk == 1
    assert second.risk == 1
