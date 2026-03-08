from __future__ import annotations


class RoutingService:
    def __init__(
        self,
        *,
        fast_track_min_score: float = 4.0,
        fast_track_max_risk: int = 1,
        high_risk_threshold: int = 4,
    ) -> None:
        self.fast_track_min_score = fast_track_min_score
        self.fast_track_max_risk = fast_track_max_risk
        self.high_risk_threshold = high_risk_threshold

    def route_candidate(self, *, final_score: float, risk_score: int) -> str:
        if risk_score >= self.high_risk_threshold:
            return "risk_priority"
        if final_score >= self.fast_track_min_score and risk_score <= self.fast_track_max_risk:
            return "fast_track"
        return "review_queue"
