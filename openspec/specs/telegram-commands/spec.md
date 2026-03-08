## Purpose

Provides telegram integration for telegram-commands.

## Requirements

### Requirement: /pending command
The system SHALL respond to the `/pending` bot command by listing all pending review items. Each item SHALL be displayed as a compact summary showing the first complete sentence of the threads draft (or english draft), falling back to a truncated summary when needed, plus the final score and risk tags. The list SHALL show at most 10 items. If there are no pending items, the system SHALL reply with a message indicating the queue is empty.

#### Scenario: Pending items exist
- **WHEN** the operator sends `/pending` and there are 3 pending review items
- **THEN** the system SHALL reply with a numbered list of 3 items, each showing a readable first-sentence summary, score, and risk tags

#### Scenario: No pending items
- **WHEN** the operator sends `/pending` and there are zero pending items
- **THEN** the system SHALL reply with "No pending review items."

#### Scenario: More than 10 pending items
- **WHEN** the operator sends `/pending` and there are 15 pending items
- **THEN** the system SHALL show the first 10 items and indicate "… and 5 more"

### Requirement: /review command
The system SHALL respond to `/review <number>` by showing the full details for the numbered item in the current pending ordering. The response SHALL include the original draft, translated draft, original comments, translated comments, and Threads draft, with the Threads draft shown after the comments for easier review. The final message in the sequence SHALL include the inline action buttons.

#### Scenario: Review a pending item
- **WHEN** the operator sends `/review 2` and the second pending review item exists
- **THEN** the system SHALL send the full review details in a readable multi-message layout, ending with the Threads draft and inline action buttons

#### Scenario: Invalid review index
- **WHEN** the operator sends `/review` without a number, or `/review 99` for a missing item
- **THEN** the system SHALL reply with usage help or a not-found message instead of crashing

### Requirement: /ingest command
The system SHALL respond to the `/ingest` bot command by triggering one ingestion+review cycle. When no extra arguments are provided, it SHALL use upstream Moltbook API parameters `time=hour`, `sort=top`, and `limit=100`. The command SHALL also accept optional `time`, `sort`, and `limit` tokens in any order, where `time` is one of `hour/day/week/month/all`, `sort` is one of `hot/new/top/rising`, and `limit` is a positive integer. Since the ingestion cycle may take a long time (involving AI scoring and translation), the system SHALL immediately reply with a confirmation that ingestion has started, then run the cycle as a background task. Upon completion, the system SHALL send a follow-up message with the ingestion parameters and resulting metrics.

#### Scenario: Trigger ingestion
- **WHEN** the operator sends `/ingest`
- **THEN** the system SHALL immediately reply with "Ingestion started…" and start the ingestion cycle as a background task

#### Scenario: Trigger ingestion with any-order arguments
- **WHEN** the operator sends `/ingest 20 new month`
- **THEN** the system SHALL run one ingestion cycle using `time=month`, `sort=new`, and `limit=20`

#### Scenario: Invalid ingestion argument
- **WHEN** the operator sends `/ingest banana`
- **THEN** the system SHALL reply with usage help instead of starting ingestion

#### Scenario: Ingestion completes
- **WHEN** a background ingestion cycle completes successfully
- **THEN** the system SHALL send a follow-up message with time, sort, limit, fetched count, persisted count, filtered duplicate count, and review items created

#### Scenario: Ingestion fails
- **WHEN** a background ingestion cycle fails with an error
- **THEN** the system SHALL send a follow-up message with the error description

### Requirement: /publish command
The system SHALL respond to the `/publish` bot command by triggering one publish cycle. The system SHALL immediately reply with a confirmation, run the cycle as a background task, and send a follow-up message with publish metrics upon completion.

#### Scenario: Trigger publish
- **WHEN** the operator sends `/publish`
- **THEN** the system SHALL immediately reply with "Publish cycle started…" and run the publish cycle as a background task

#### Scenario: Publish completes
- **WHEN** a background publish cycle completes
- **THEN** the system SHALL send a follow-up message with scheduled, published, retry, and failed counts

### Requirement: /stats command
The system SHALL respond to the `/stats` bot command by querying and displaying pipeline statistics. The statistics SHALL include: total pending count, total approved count (today), total rejected count (today), total published count (today), and the top 3 highest-scoring pending items with their truncated titles and scores.

#### Scenario: Stats with activity
- **WHEN** the operator sends `/stats` and there has been pipeline activity today
- **THEN** the system SHALL reply with a formatted summary showing counts and top pending items

#### Scenario: Stats with no activity
- **WHEN** the operator sends `/stats` and there has been no activity today
- **THEN** the system SHALL reply with zero counts and "No pending items"

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

### Requirement: /cancel command
The system SHALL respond to the `/cancel` bot command by cancelling any active comment-collection or edit-collection state for the chat.

#### Scenario: Cancel active state
- **WHEN** the operator sends `/cancel` while in comment-collection or edit-collection state
- **THEN** the system SHALL clear the pending state and reply with "Cancelled."

#### Scenario: Cancel with no active state
- **WHEN** the operator sends `/cancel` with no active pending interaction
- **THEN** the system SHALL reply with "Nothing to cancel."

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

### Requirement: Unknown message handling
The system SHALL respond to any unrecognized text message (not a command, not in a collection state) with a help hint suggesting the operator use `/help` to see available commands.

#### Scenario: Unknown text message
- **WHEN** the operator sends a plain text message that is not a recognized command and no collection state is active
- **THEN** the system SHALL reply with "Unknown command. Use /help to see available commands."

### Requirement: Setup documentation
The system SHALL include a `docs/telegram-setup.md` documentation file covering: BotFather registration steps, how to discover the chat ID, environment variable configuration, HTTPS and port requirements for webhooks, and verification steps.

#### Scenario: Documentation exists
- **WHEN** the implementation is complete
- **THEN** a `docs/telegram-setup.md` file SHALL exist with complete setup instructions
