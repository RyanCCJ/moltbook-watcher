## MODIFIED Requirements

### Requirement: /help command

The system SHALL respond to the `/help` bot command by listing all available commands with brief descriptions.

#### Scenario: Show help

- **WHEN** the operator sends `/help`
- **THEN** the system SHALL reply with a formatted list of all supported commands: `/pending`, `/review <number>`, `/ingest [time] [sort] [limit]`, `/publish`, `/regenerate [number]`, `/recall`, `/stats`, `/health`, `/help`, and `/cancel`

## ADDED Requirements

### Requirement: /regenerate command in Telegram

The system SHALL respond to the `/regenerate` bot command by re-running Phase 2 (translation + Threads draft generation) for pending review items with empty content. When no argument is provided, the system SHALL process all pending review items with empty `chinese_translation_full` or empty `threads_draft`. When a numeric argument is provided (`/regenerate <N>`), it SHALL target the Nth item from the current `/pending` list. Since regeneration may take a long time (involving multiple Ollama calls), the system SHALL immediately reply with a confirmation that regeneration has started, then run the cycle as a background task. Upon completion, the system SHALL send a follow-up message with the regeneration metrics.

#### Scenario: Trigger regeneration of all empty items

- **WHEN** the operator sends `/regenerate` and there are 5 pending items with empty content
- **THEN** the system SHALL immediately reply with "Regeneration started… (5 items)" and start the regeneration cycle as a background task

#### Scenario: Trigger regeneration of a specific item

- **WHEN** the operator sends `/regenerate 3` and the third pending item exists
- **THEN** the system SHALL immediately reply with "Regeneration started… (1 item)" and regenerate that specific item as a background task

#### Scenario: Regeneration completes

- **WHEN** a background regeneration cycle completes successfully
- **THEN** the system SHALL send a follow-up message with regenerated count, skipped count, and failed count

#### Scenario: No items to regenerate

- **WHEN** the operator sends `/regenerate` and all pending items already have content
- **THEN** the system SHALL reply with "No items need regeneration."

#### Scenario: Invalid regeneration index

- **WHEN** the operator sends `/regenerate 99` and there are fewer than 99 pending items
- **THEN** the system SHALL reply with "Review item number not found in the current pending list."
