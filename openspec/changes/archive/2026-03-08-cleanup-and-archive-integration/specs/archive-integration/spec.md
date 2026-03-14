## ADDED Requirements

### Requirement: Daily automatic archival of stale review items
The system SHALL automatically archive pending review items whose associated candidate post was captured more than 14 days ago. The archival SHALL run once per day, immediately before the daily summary is built, using the same schedule as the daily summary (`TELEGRAM_DAILY_SUMMARY_HOUR` / `TELEGRAM_DAILY_SUMMARY_TIMEZONE`). Archived items SHALL have their review decision set to `"archived"` and `reviewed_by` set to `"archive-worker"`. The associated candidate post status SHALL transition to `ARCHIVED`.

#### Scenario: Stale items exist
- **WHEN** the daily archive runs and there are 3 pending review items with `captured_at` older than 14 days
- **THEN** the system SHALL archive all 3 items, setting `decision="archived"` and `reviewed_by="archive-worker"` on each review item, and transitioning each candidate post to `ARCHIVED` status

#### Scenario: No stale items
- **WHEN** the daily archive runs and all pending review items have `captured_at` within the last 14 days
- **THEN** the system SHALL archive zero items and proceed to build the daily summary

#### Scenario: Telegram not configured
- **WHEN** Telegram is not configured (no bot token or chat ID)
- **THEN** the daily archive SHALL NOT run, since it is coupled to the daily summary cycle

### Requirement: Archive stats in daily summary
The daily summary Telegram message SHALL include archive statistics: the count of items auto-archived in this cycle, and a list of any newly archived items that had a `final_score >= 4.0` (high-score recalls). Each high-score recall entry SHALL show the source URL and final score.

#### Scenario: Items archived with high-score recalls
- **WHEN** the daily archive archives 5 items and 2 of them have `final_score >= 4.0`
- **THEN** the daily summary message SHALL include "Auto-archived: 5" and list the 2 high-score items with their source URLs and scores

#### Scenario: Items archived with no high-score recalls
- **WHEN** the daily archive archives 3 items and none have `final_score >= 4.0`
- **THEN** the daily summary message SHALL include "Auto-archived: 3" and omit the high-score recall section

#### Scenario: No items archived
- **WHEN** the daily archive archives zero items
- **THEN** the daily summary message SHALL include "Auto-archived: 0" and omit the high-score recall section

### Requirement: Archive runs before summary stats
The daily archive step SHALL complete and commit its changes before the daily summary stats are queried. This ensures the summary counts (pending, etc.) reflect the post-archive state.

#### Scenario: Summary reflects post-archive state
- **WHEN** there are 10 pending items and 4 are stale (older than 14 days)
- **THEN** the daily summary SHALL show pending count as 6 (after archiving 4), not 10
