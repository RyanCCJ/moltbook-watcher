## MODIFIED Requirements

### Requirement: Generate Threads draft for qualifying posts
The system SHALL generate a Threads-optimized draft post using Ollama (with `think=True`) when a candidate post's `final_score` meets or exceeds the `REVIEW_MIN_SCORE` threshold from Settings. The threshold SHALL be configurable via the `REVIEW_MIN_SCORE` environment variable instead of being hardcoded. Since only posts meeting `REVIEW_MIN_SCORE` enter the review queue, all review items that are created SHALL have draft generation attempted (provided `source_url` is non-empty).

#### Scenario: Post meets configurable score threshold
- **WHEN** a review payload is built for a post whose `final_score` meets `REVIEW_MIN_SCORE` (read from Settings)
- **THEN** the system calls `ReviewPayloadService._generate_threads_draft()` with the raw content, top comments, score, and source URL, and stores the result in the `threads_draft` field of `ReviewItem`

#### Scenario: Post does not meet score threshold
- **WHEN** a post's `final_score` is below `REVIEW_MIN_SCORE`
- **THEN** the post is archived by `IngestionWorker` and no `ReviewItem` is created at all (no draft generation call is made)

#### Scenario: Draft generation fails
- **WHEN** Ollama returns an error or empty response during draft generation
- **THEN** the system logs a warning, sets `threads_draft` to an empty string, and continues without failing the review item creation
