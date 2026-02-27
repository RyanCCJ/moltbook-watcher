from __future__ import annotations


class PublishRetryPolicy:
    def __init__(self, max_attempts: int = 3, base_delay_seconds: int = 0) -> None:
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds

    def should_retry(self, *, attempt_count: int) -> bool:
        return attempt_count < self.max_attempts

    def next_delay_seconds(self, *, attempt_count: int) -> int:
        return self.base_delay_seconds * (2 ** max(0, attempt_count - 1))
