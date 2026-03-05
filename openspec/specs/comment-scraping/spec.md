# Capability: Comment Scraping

## Purpose
Scrape and store top comments from Moltbook posts to provide community context for scoring and translation.

## Requirements

### Requirement: Fetch top comments for each ingested post

The system SHALL fetch the top N comments for each post during ingestion by calling the Moltbook API endpoint `GET /posts/{POST_ID}/comments?sort=top&limit=N`. The default comment limit SHALL be 5 per post.

#### Scenario: Successfully fetch comments for a post

- **WHEN** the ingestion worker processes a new post with `source_post_id` available
- **THEN** the system calls `MoltbookAPIClient.fetch_comments(post_id, limit=5, sort="top")` and attaches the returned comments to the `MoltbookPost` dataclass

#### Scenario: Moltbook comments endpoint is unavailable

- **WHEN** the comments API call fails (timeout, HTTP error, or network error)
- **THEN** the system logs a warning and continues processing with an empty comments list — the post is still scored and persisted without comment context

#### Scenario: Post has fewer comments than the configured limit

- **WHEN** a post has fewer than N comments (including zero)
- **THEN** the system returns all available comments without error

### Requirement: Include comments in scoring prompt

The system SHALL include the text of fetched top comments in the Ollama scoring prompt alongside the post content, so the LLM can factor community reaction into its scoring assessment.

#### Scenario: Post has comments available

- **WHEN** a post is scored and has one or more fetched comments
- **THEN** the scoring prompt sent to Ollama includes both the post content and a section listing the top comment texts with their author handles

#### Scenario: Post has no comments

- **WHEN** a post is scored with an empty comments list
- **THEN** the scoring prompt contains only the post content (same as current behavior), and scoring proceeds normally

### Requirement: Store comment snapshots in ReviewItem

The system SHALL store the original comment texts as a JSON list in the `top_comments_snapshot` column on `ReviewItem`. If translation is configured (via `TRANSLATION_LANGUAGE`), the system SHALL also store translated comment texts in the `top_comments_translated` column.

#### Scenario: Review item created with comments and translation enabled

- **WHEN** a review item is created for a post that has fetched comments and `TRANSLATION_LANGUAGE` is set
- **THEN** the `top_comments_snapshot` column contains a JSON list of original comment objects (author, content) and `top_comments_translated` contains the translated versions

#### Scenario: Review item created with comments but no translation

- **WHEN** a review item is created for a post that has fetched comments and `TRANSLATION_LANGUAGE` is empty
- **THEN** the `top_comments_snapshot` column contains the original comment objects and `top_comments_translated` is an empty JSON list

#### Scenario: Review item created for a post with no comments

- **WHEN** a review item is created for a post that has no fetched comments
- **THEN** both `top_comments_snapshot` and `top_comments_translated` are empty JSON lists

### Requirement: MoltbookPost dataclass includes comments

The `MoltbookPost` dataclass SHALL include a `top_comments` field of type `list[MoltbookComment]` (default empty list), where `MoltbookComment` is a new dataclass containing `author_handle: str | None`, `content_text: str`, and `upvotes: int`.

#### Scenario: MoltbookPost created with comments

- **WHEN** a post is parsed and comments have been fetched
- **THEN** the `top_comments` field contains a list of `MoltbookComment` instances parsed from the API response

#### Scenario: MoltbookPost created without fetching comments

- **WHEN** a post is parsed before comment fetching or when comments are unavailable
- **THEN** the `top_comments` field defaults to an empty list
