from src.services.routing_service import RoutingService


def test_routing_service_applies_thresholds() -> None:
    service = RoutingService(fast_track_min_score=4.2, high_risk_threshold=4)

    assert service.route_candidate(final_score=4.6, risk_score=1) == "fast_track"
    assert service.route_candidate(final_score=3.8, risk_score=4) == "risk_priority"
    assert service.route_candidate(final_score=3.8, risk_score=2) == "review_queue"


def test_routing_service_supports_custom_fast_track_risk_threshold() -> None:
    service = RoutingService(fast_track_min_score=3.6, fast_track_max_risk=2)

    assert service.route_candidate(final_score=3.7, risk_score=2) == "fast_track"
    assert service.route_candidate(final_score=3.5, risk_score=2) == "review_queue"
