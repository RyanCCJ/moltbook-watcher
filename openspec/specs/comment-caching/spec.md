# Capability: Comment Caching

## Purpose
TBD: Persist fetched comments to the database during ingestion to avoid redundant API calls during the review phase.

## Requirements

### Requirement: Ingestion worker persists top comments

The `IngestionWorker` SHALL store the top comments fetched during ingestion into the `candidate_posts` record as a JSON-serialized `top_comments_snapshot` column. The snapshot SHALL contain a list of objects with keys `author_handle`, `content_text`, and `upvotes`.

#### Scenario: Post with comments is ingested

- **WHEN** the ingestion worker fetches a post with `source_post_id` and successfully retrieves 3 top comments
- **THEN** the `candidate_posts` record's `top_comments_snapshot` column contains a JSON array with 3 objects, each having `author_handle`, `content_text`, and `upvotes` fields

#### Scenario: Post with no comments is ingested

- **WHEN** the ingestion worker fetches a post with `source_post_id` but the comments API returns an empty list
- **THEN** the `candidate_posts` record's `top_comments_snapshot` column contains an empty JSON array `[]`

#### Scenario: Post with no source_post_id

- **WHEN** the ingestion worker processes a post where `source_post_id` is `None`
- **THEN** the `candidate_posts` record's `top_comments_snapshot` column contains an empty JSON array `[]` (no comments fetch is attempted)

### Requirement: Review worker reads cached comments

The `ReviewWorker` SHALL read top comments from the `candidate_posts.top_comments_snapshot` column instead of calling `MoltbookAPIClient.fetch_comments()`. The review worker SHALL NOT make any Moltbook API calls for comments.

#### Scenario: Review worker processes candidate with cached comments

- **WHEN** the review worker processes a queued candidate that has a non-empty `top_comments_snapshot`
- **THEN** the review worker deserializes the snapshot into `MoltbookComment` objects and passes them to `ReviewPayloadService.build_payload()` without calling the Moltbook API

#### Scenario: Review worker processes candidate with empty snapshot

- **WHEN** the review worker processes a queued candidate where `top_comments_snapshot` is `[]`
- **THEN** the review worker passes an empty list to `build_payload()` without calling the Moltbook API

### Requirement: Database schema includes top_comments_snapshot column

The `candidate_posts` table SHALL have a `top_comments_snapshot` column of type `JSON` (or equivalent), defaulting to an empty JSON array. A database migration SHALL be provided to add this column.

#### Scenario: New column exists after migration

- **WHEN** the database migration is applied
- **THEN** the `candidate_posts` table has a `top_comments_snapshot` column with a default value of `[]`

#### Scenario: Existing records have default value

- **WHEN** the migration runs on a database with existing `candidate_posts` records
- **THEN** all existing records have `top_comments_snapshot` set to `[]`
