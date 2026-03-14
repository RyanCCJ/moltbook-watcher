## MODIFIED Requirements

### Requirement: /health command
The system SHALL respond to the `/health` bot command by checking the system health (database connectivity, webhook registration status) and replying with the health status. The health check SHALL NOT include Redis/queue connectivity since the queue infrastructure has been removed.

#### Scenario: System healthy
- **WHEN** the operator sends `/health` and all subsystems are healthy
- **THEN** the system SHALL reply with status "ok", database status, and webhook confirmation

#### Scenario: System degraded
- **WHEN** the operator sends `/health` and the database is unreachable
- **THEN** the system SHALL reply with status "degraded" and list the failing subsystems

### Requirement: /help command
The system SHALL respond to the `/help` bot command by listing all available commands with brief descriptions.

#### Scenario: Show help
- **WHEN** the operator sends `/help`
- **THEN** the system SHALL reply with a formatted list of all supported commands: `/pending`, `/review <number>`, `/ingest [time] [sort] [limit]`, `/publish`, `/recall`, `/stats`, `/health`, `/help`, and `/cancel`

### Requirement: Daily summary
The system SHALL send a daily summary message at the hour configured by `TELEGRAM_DAILY_SUMMARY_HOUR` in the timezone configured by `TELEGRAM_DAILY_SUMMARY_TIMEZONE`. Before building the summary, the system SHALL run the daily archive cycle. The summary SHALL include: date, total ingested posts (today), pending count (post-archive), approved count (today), rejected count (today), published count (today), failed job count (today), auto-archived count (this cycle), high-score recalls (newly archived items with `final_score >= 4.0`), and the top 3 highest-scoring pending items.

#### Scenario: Daily summary with data
- **WHEN** the scheduled daily summary fires and there has been pipeline activity
- **THEN** the system SHALL send a formatted summary message to the configured Telegram chat, including archive stats

#### Scenario: Daily summary with no activity
- **WHEN** the scheduled daily summary fires and there has been no activity
- **THEN** the system SHALL send a summary showing zero counts including "Auto-archived: 0"

#### Scenario: Telegram not configured
- **WHEN** the daily summary job fires but `TELEGRAM_BOT_TOKEN` is not configured
- **THEN** the system SHALL skip the summary silently
