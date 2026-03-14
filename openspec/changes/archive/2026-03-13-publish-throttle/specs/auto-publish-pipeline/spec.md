# Capability: Auto-publish Pipeline (Delta)

## MODIFIED Requirements

### Requirement: PublishControlService updated for semi-auto
The `PublishControlService.can_auto_publish()` method SHALL be called by the pipeline when `PUBLISH_MODE=semi-auto`. The method SHALL check both the publish mode and the `risk_score` threshold. The `MAX_PUBLISH_PER_DAY` setting SHALL accept values between 0 and 10 (previously capped at 5).

#### Scenario: can_auto_publish returns true
- **WHEN** `publish_mode` is `semi-auto`, the system is not paused, and `risk_score <= 1`
- **THEN** `can_auto_publish()` SHALL return `True`

#### Scenario: can_auto_publish when paused
- **WHEN** `publish_mode` is `semi-auto` but publishing is paused
- **THEN** `can_auto_publish()` SHALL return `False`

#### Scenario: max_publish_per_day set to 6
- **WHEN** `MAX_PUBLISH_PER_DAY=6` is configured in `.env`
- **THEN** the application SHALL accept and use the value without validation error
