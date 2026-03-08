# Capability: Configurable Ingestion

## Purpose
Make all ingestion parameters configurable via environments variables to enable iteration without code changes.

## Requirements

### Requirement: Ingestion time parameter from environment variable
The system SHALL read the default ingestion time window from the `INGESTION_TIME` environment variable in Settings. The value MUST be one of `hour`, `day`, `week`, `month`, or `all`. The default value SHALL be `hour`.

#### Scenario: INGESTION_TIME set to month
- **WHEN** `INGESTION_TIME=month` is configured in `.env`
- **THEN** the scheduler, runtime, and all default ingestion calls SHALL use `time="month"` unless explicitly overridden

#### Scenario: INGESTION_TIME not set
- **WHEN** the `INGESTION_TIME` variable is absent from `.env`
- **THEN** the system SHALL default to `time="hour"`

#### Scenario: Invalid INGESTION_TIME value
- **WHEN** `INGESTION_TIME=invalid` is configured
- **THEN** the application SHALL fail at startup with a validation error from pydantic-settings

### Requirement: Ingestion limit parameter from environment variable
The system SHALL read the default ingestion post limit from the `INGESTION_LIMIT` environment variable in Settings. The value MUST be an integer between 1 and 200 (inclusive). The default value SHALL be `20`.

#### Scenario: INGESTION_LIMIT set to 50
- **WHEN** `INGESTION_LIMIT=50` is configured in `.env`
- **THEN** the scheduler, runtime, ops API, and all default ingestion calls SHALL use `limit=50` unless explicitly overridden

#### Scenario: INGESTION_LIMIT not set
- **WHEN** the `INGESTION_LIMIT` variable is absent from `.env`
- **THEN** the system SHALL default to `limit=20`

### Requirement: Ingestion sort parameter from environment variable
The system SHALL read the default ingestion sort order from the `INGESTION_SORT` environment variable in Settings. The value MUST be one of `hot`, `new`, `top`, or `rising`. The default value SHALL be `top`.

#### Scenario: INGESTION_SORT set to new
- **WHEN** `INGESTION_SORT=new` is configured in `.env`
- **THEN** the scheduler, runtime, and all default ingestion calls SHALL use `sort="new"` unless explicitly overridden

#### Scenario: INGESTION_SORT not set
- **WHEN** the `INGESTION_SORT` variable is absent from `.env`
- **THEN** the system SHALL default to `sort="top"`

### Requirement: All entry points read defaults from Settings
The scheduler (`scheduler.py`), runtime (`runtime.py`), ops API (`ops_routes.py`), and Telegram routes (`telegram_routes.py`) SHALL read ingestion defaults (time, limit, sort) from Settings rather than using hardcoded values.

#### Scenario: Scheduler uses configured defaults
- **WHEN** the scheduler triggers an ingestion cycle
- **THEN** it SHALL call `run_ingestion_once()` with `time`, `limit`, and `sort` values from Settings

#### Scenario: Ops API uses configured defaults
- **WHEN** a `POST /ops/ingestion/run` request is sent without query parameters
- **THEN** the endpoint SHALL use `time`, `limit`, and `sort` from Settings as defaults

### Requirement: Telegram and CLI override capability
The Telegram `/ingest` command and CLI SHALL allow the operator to override the environment-variable defaults for a single invocation. When override arguments are provided, they SHALL take precedence over Settings values.

#### Scenario: Telegram ingest with override
- **WHEN** the operator sends `/ingest all top 100` via Telegram
- **THEN** the system SHALL run ingestion with `time="all"`, `sort="top"`, `limit=100`, ignoring the Settings defaults for that invocation

#### Scenario: Telegram ingest without override
- **WHEN** the operator sends `/ingest` via Telegram with no arguments
- **THEN** the system SHALL run ingestion using the Settings defaults (`INGESTION_TIME`, `INGESTION_SORT`, `INGESTION_LIMIT`)

#### Scenario: CLI ingest with partial override
- **WHEN** the operator runs `ops_cli.py ingest --limit 50` without specifying time or sort
- **THEN** the system SHALL use `limit=50` from the CLI argument and `time` and `sort` from Settings
