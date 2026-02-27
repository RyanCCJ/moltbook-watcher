import logging

from src.services.logging_service import get_logger, redact_secrets


def test_redact_secrets_masks_sensitive_values() -> None:
    payload = {
        "api_token": "secret-token",
        "smtp_password": "super-secret",
        "normal_field": "ok",
    }

    redacted = redact_secrets(payload)

    assert redacted["api_token"] == "***REDACTED***"
    assert redacted["smtp_password"] == "***REDACTED***"
    assert redacted["normal_field"] == "ok"


def test_structured_logger_never_emits_raw_credentials(caplog) -> None:
    caplog.set_level(logging.INFO)
    logger = get_logger("security-test")

    logger.info("credential_check", api_token="abc123", normal="visible")

    assert "abc123" not in caplog.text
    assert "***REDACTED***" in caplog.text
