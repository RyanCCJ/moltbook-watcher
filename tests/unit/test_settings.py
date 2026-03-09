import pytest
from pydantic import ValidationError

from src.config.settings import Settings


def test_settings_default_ollama_timeout_seconds() -> None:
    assert Settings().ollama_timeout_seconds == 300


def test_settings_rejects_ollama_timeout_below_minimum() -> None:
    with pytest.raises(ValidationError):
        Settings(ollama_timeout_seconds=29)
