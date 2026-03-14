from __future__ import annotations

from src.config.settings import get_settings


class PublishControlService:
    def __init__(self, initial_mode: str = "manual-approval") -> None:
        self._mode = initial_mode
        self._paused = False

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def paused(self) -> bool:
        return self._paused

    def switch_mode(self, mode: str, reason: str | None = None) -> None:
        _ = reason
        if mode not in {"manual-approval", "semi-auto"}:
            raise ValueError("Invalid publish mode")
        self._mode = mode

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def can_publish_anything(self) -> bool:
        return not self._paused

    def can_auto_publish(self, *, risk_score: int) -> bool:
        if self._paused:
            return False
        if self._mode == "manual-approval":
            return False
        return risk_score <= 1


publish_control = PublishControlService(initial_mode=get_settings().publish_mode)
