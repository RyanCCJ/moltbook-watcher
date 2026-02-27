# Moltbook Source Contract (MVP)

## Purpose

Define the source-ingestion contract for reading Moltbook content through API
capabilities described in `https://www.moltbook.com/skill.md`.

## Contract Scope

- Source integration must use API access path and not HTML crawling for MVP.
- Source windows supported by ingestion:
  - `all_time`
  - `year`
  - `month`
  - `week`
  - `today`
  - `past_hour`

## Logical Interface

### Operation: list_posts

Input:
- `window` (required, enum)
- `cursor` (optional)
- `limit` (optional)

Output item fields (minimum required by pipeline):
- `source_url` (required)
- `source_post_id` (optional but preferred)
- `author_handle` (optional)
- `content_text` (required)
- `created_at` (required)
- `engagement_summary` (optional)

## Failure Semantics

- Recoverable source errors must be retried with backoff.
- Terminal source failures must be logged with structured details.
- Partial fetch results must not corrupt candidate lifecycle state.

## Compatibility Notes

- API adapter must isolate platform-specific request/response details behind this
  contract to keep scoring and review workflows stable when source API evolves.
