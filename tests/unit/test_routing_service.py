from src.services.routing_service import RoutingService


def test_routing_service_applies_thresholds() -> None:
    service = RoutingService(fast_track_threshold=4.2, high_risk_threshold=4)

    assert service.route_candidate(final_score=4.6, risk_score=1) == "fast_track"
    assert service.route_candidate(final_score=3.8, risk_score=4) == "risk_priority"
    assert service.route_candidate(final_score=3.8, risk_score=2) == "review_queue"


def test_follow_up_gate_checks_novelty_delta_and_cooldown() -> None:
    service = RoutingService()

    assert service.is_follow_up_allowed(novelty_delta_score=1.2, days_since_previous_publish=8)
    assert not service.is_follow_up_allowed(novelty_delta_score=0.9, days_since_previous_publish=8)
    assert not service.is_follow_up_allowed(novelty_delta_score=1.2, days_since_previous_publish=3)
