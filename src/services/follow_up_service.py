from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(slots=True)
class FollowUpEvaluation:
    is_eligible: bool
    justification: str
    eligible_after: datetime


class FollowUpService:
    def __init__(self, min_novelty_delta: float = 1.0, cooldown_days: int = 7) -> None:
        self.min_novelty_delta = min_novelty_delta
        self.cooldown_days = cooldown_days

    def evaluate(self, *, novelty_delta_score: float, prior_published_at: datetime) -> FollowUpEvaluation:
        eligible_after = prior_published_at.astimezone(UTC) + timedelta(days=self.cooldown_days)
        now = datetime.now(tz=UTC)

        if novelty_delta_score < self.min_novelty_delta:
            return FollowUpEvaluation(
                is_eligible=False,
                justification="Novelty delta below threshold",
                eligible_after=eligible_after,
            )

        if now < eligible_after:
            return FollowUpEvaluation(
                is_eligible=False,
                justification="Cooldown not met",
                eligible_after=eligible_after,
            )

        return FollowUpEvaluation(
            is_eligible=True,
            justification="Novelty and cooldown thresholds satisfied",
            eligible_after=eligible_after,
        )
