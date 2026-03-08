# Capability: Ingestion Digest Notification

## Purpose
Replace per-item push notifications with a single Telegram digest summary per ingestion cycle.

## Requirements

### Requirement: Ingestion digest summary replaces per-item push
After each ingestion cycle, the system SHALL send a single Telegram digest message summarizing the cycle results instead of pushing individual review item messages. The digest SHALL be sent only when new posts are persisted (`persisted_count > 0`).

#### Scenario: Ingestion cycle with new posts
- **WHEN** an ingestion cycle completes and 12 new posts were persisted (8 queued, 4 archived)
- **THEN** the system SHALL send one Telegram digest message containing: total fetched count, new post count, filtered count, score breakdown by band, risk summary, auto-publish readiness count, and total pending review count

#### Scenario: Ingestion cycle with no new posts
- **WHEN** an ingestion cycle completes and 0 new posts were persisted (all deduplicated)
- **THEN** the system SHALL NOT send any Telegram message

### Requirement: Digest includes score distribution breakdown
The digest message SHALL include a score breakdown showing the count of posts in each score band: `>= AUTO_PUBLISH_MIN_SCORE` (marked with ⭐), `>= REVIEW_MIN_SCORE` (marked with ✅), and `< REVIEW_MIN_SCORE` (marked with 📦). The thresholds SHALL be read from Settings.

#### Scenario: Score breakdown in digest
- **WHEN** an ingestion cycle produces 3 posts scoring >= 4.0, 5 posts scoring 3.5-3.99, and 4 posts scoring < 3.5
- **THEN** the digest SHALL display:
  - `⭐ >= 4.0: 3 posts`
  - `✅ >= 3.5: 5 posts (queued)`
  - `📦 < 3.5: 4 posts (archived)`

### Requirement: Digest includes auto-publish readiness
The digest message SHALL include a line showing how many posts would qualify for auto-publish (meeting both `AUTO_PUBLISH_MIN_SCORE` and `risk_score <= 1`), regardless of the current `PUBLISH_MODE` setting. This provides ongoing observation data for transitioning to semi-auto mode.

#### Scenario: Auto-publish readiness in manual mode
- **WHEN** `PUBLISH_MODE=manual-approval` and 2 posts in the cycle meet auto-publish criteria
- **THEN** the digest SHALL display `Auto-publish: 2 would qualify`

#### Scenario: Auto-publish readiness in semi-auto mode
- **WHEN** `PUBLISH_MODE=semi-auto` and 2 posts were auto-approved
- **THEN** the digest SHALL display `Auto-publish: 2 auto-approved`

### Requirement: Digest includes pending review total
The digest message SHALL include the total number of pending review items across all cycles, allowing the operator to gauge workload before opening `/pending`.

#### Scenario: Pending count in digest
- **WHEN** there are 23 total pending review items in the database
- **THEN** the digest SHALL display `Pending review: 23 total`

### Requirement: Digest ends with review command hint
The digest message SHALL end with `/pending to review` to remind the operator how to access pending items.

#### Scenario: Command hint present
- **WHEN** a digest message is sent
- **THEN** the last line SHALL be `/pending to review`

### Requirement: format_ingestion_digest method on TelegramService
`TelegramService` SHALL expose a `format_ingestion_digest()` method that accepts cycle metrics (fetched count, persisted count, score breakdown, risk breakdown, auto-publish count, pending total) and returns a formatted Telegram message string.

#### Scenario: Format digest message
- **WHEN** `format_ingestion_digest()` is called with cycle metrics
- **THEN** it SHALL return a properly formatted string containing all required sections
