from __future__ import annotations

import json
import logging
from typing import Any

_SENSITIVE_KEY_HINTS = ("token", "password", "secret", "key")


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


class StructuredLogger:
    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def info(self, event: str, **fields: Any) -> None:
        self._logger.info(_render_event(event, fields))

    def warning(self, event: str, **fields: Any) -> None:
        self._logger.warning(_render_event(event, fields))

    def error(self, event: str, **fields: Any) -> None:
        self._logger.error(_render_event(event, fields))


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)


def _render_event(event: str, fields: dict[str, Any]) -> str:
    payload = {"event": event, **redact_secrets(fields)}
    return json.dumps(payload, default=str, sort_keys=True)


def redact_secrets(fields: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in fields.items():
        key_lower = key.lower()
        if any(hint in key_lower for hint in _SENSITIVE_KEY_HINTS):
            redacted[key] = "***REDACTED***"
            continue
        redacted[key] = value
    return redacted
