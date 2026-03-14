## ADDED Requirements

### Requirement: /regenerate command re-runs Phase 2 for empty review items

The system SHALL respond to the `/regenerate` Telegram command by re-running Phase 2 (translation + Threads draft generation) for pending review items with empty content. When no argument is provided, the system SHALL find all pending review items where `chinese_translation_full` is empty OR `threads_draft` is empty, and regenerate them sequentially. When a numeric argument is provided (`/regenerate <N>`), the system SHALL target the Nth item from the current `/pending` list ordering. The command SHALL run as a background task (same pattern as `/ingest`) to prevent webhook timeout.

#### Scenario: Regenerate all empty items (no argument)

- **WHEN** the operator sends `/regenerate` and there are 5 pending review items with empty `chinese_translation_full` or empty `threads_draft`
- **THEN** the system SHALL immediately reply with "Regeneration started… (5 items)", run regeneration as a background task, and send a follow-up message with the count of successfully regenerated items on completion

#### Scenario: Regenerate a specific item by index

- **WHEN** the operator sends `/regenerate 3` and the third item in the current `/pending` list exists
- **THEN** the system SHALL immediately reply with "Regeneration started… (1 item)", re-run Phase 2 for that specific review item, and send a follow-up message with the result

#### Scenario: Regenerate with invalid index

- **WHEN** the operator sends `/regenerate 99` and there are only 10 pending items
- **THEN** the system SHALL reply with "Review item number not found in the current pending list."

#### Scenario: No items need regeneration

- **WHEN** the operator sends `/regenerate` and all pending review items already have non-empty translations and Threads drafts
- **THEN** the system SHALL reply with "No items need regeneration."

#### Scenario: Regeneration skips items with existing content (batch mode)

- **WHEN** `/regenerate` is called without arguments
- **THEN** the system SHALL skip review items that already have both non-empty `chinese_translation_full` AND non-empty `threads_draft`, regenerating only those with at least one empty field

#### Scenario: Regeneration failure for a single item

- **WHEN** regeneration is running and Ollama fails for one item (timeout or error)
- **THEN** the system SHALL log a warning, leave that item's fields unchanged, and continue processing the remaining items

### Requirement: REST API endpoint for regeneration

The system SHALL expose `POST /ops/regenerate` as a REST API endpoint. When called without query parameters, it SHALL regenerate all pending review items with empty content. When called with `review_item_id` query parameter, it SHALL regenerate only that specific review item.

#### Scenario: Regenerate all empty via REST API

- **WHEN** `POST /ops/regenerate` is called without parameters
- **THEN** the system SHALL run regeneration for all pending review items with empty translations or Threads drafts and return `{"ok": true, "metrics": {"regenerated_count": N, "skipped_count": M, "failed_count": F}}`

#### Scenario: Regenerate specific item via REST API

- **WHEN** `POST /ops/regenerate?review_item_id=<id>` is called
- **THEN** the system SHALL regenerate only the specified review item and return the result metrics

#### Scenario: Regenerate with invalid review item ID

- **WHEN** `POST /ops/regenerate?review_item_id=nonexistent` is called
- **THEN** the system SHALL return HTTP 404 with detail "Review item not found"

### Requirement: CLI subcommand for regeneration

The system SHALL provide a `regenerate` subcommand in `scripts/ops_cli.py` that calls `POST /ops/regenerate` via HTTP. When called without `--id`, it SHALL regenerate all empty items. When called with `--id <review_item_id>`, it SHALL target a specific item.

#### Scenario: CLI regenerate all

- **WHEN** the operator runs `uv run python scripts/ops_cli.py regenerate`
- **THEN** the CLI SHALL call `POST /ops/regenerate` and print the result metrics as JSON

#### Scenario: CLI regenerate specific item

- **WHEN** the operator runs `uv run python scripts/ops_cli.py regenerate --id <review_item_id>`
- **THEN** the CLI SHALL call `POST /ops/regenerate?review_item_id=<id>` and print the result

### Requirement: Makefile target for regeneration

The system SHALL include an `ops-regenerate` Makefile target that invokes the CLI regenerate command for convenience.

#### Scenario: Makefile regenerate

- **WHEN** the operator runs `make ops-regenerate`
- **THEN** the system SHALL execute `uv run python scripts/ops_cli.py regenerate`

### Requirement: Regeneration uses fresh ReviewPayloadService instance

Each invocation of the regeneration function SHALL create a new `ReviewPayloadService` instance with `_ollama_enabled = True` and a reset failure counter, so that circuit breaker state from a prior ingestion cycle does not carry over to the regeneration run.

#### Scenario: Regeneration after circuit breaker triggered

- **WHEN** an ingestion cycle disabled Ollama due to consecutive failures, and the operator then runs `/regenerate`
- **THEN** the regeneration SHALL use a fresh `ReviewPayloadService` with Ollama enabled, independent of the prior ingestion cycle's state

### Requirement: ReviewItemRepository update_payload method

The `ReviewItemRepository` SHALL provide an `update_payload` method that updates `chinese_translation_full`, `top_comments_translated`, and `threads_draft` on a single review item. The method SHALL only update fields that are provided (non-None) and SHALL require the review item to be in `pending` decision state.

#### Scenario: Update all payload fields

- **WHEN** `update_payload` is called with all three fields populated
- **THEN** the system SHALL update `chinese_translation_full`, `top_comments_translated`, and `threads_draft` on the specified review item

#### Scenario: Update on non-pending item

- **WHEN** `update_payload` is called for a review item whose decision is `approved`
- **THEN** the system SHALL raise a `ValueError` with message "Decision already submitted"
