from __future__ import annotations


class RoutingService:
    def __init__(
        self,
        *,
        fast_track_threshold: float = 4.2,
        high_risk_threshold: int = 4,
        min_follow_up_novelty_delta: float = 1.0,
        follow_up_cooldown_days: int = 7,
    ) -> None:
        self.fast_track_threshold = fast_track_threshold
        self.high_risk_threshold = high_risk_threshold
        self.min_follow_up_novelty_delta = min_follow_up_novelty_delta
        self.follow_up_cooldown_days = follow_up_cooldown_days

    def route_candidate(self, *, final_score: float, risk_score: int) -> str:
        if risk_score >= self.high_risk_threshold:
            return "risk_priority"
        if final_score >= self.fast_track_threshold and risk_score <= 1:
            return "fast_track"
        return "review_queue"

    def is_follow_up_allowed(self, *, novelty_delta_score: float, days_since_previous_publish: int) -> bool:
        return (
            novelty_delta_score >= self.min_follow_up_novelty_delta
            and days_since_previous_publish >= self.follow_up_cooldown_days
        )
