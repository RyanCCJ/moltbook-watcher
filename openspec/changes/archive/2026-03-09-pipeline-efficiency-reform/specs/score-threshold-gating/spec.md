## ADDED Requirements

### Requirement: Review minimum score threshold from environment variable
The system SHALL read the minimum score threshold for entering the review queue from the `REVIEW_MIN_SCORE` environment variable in Settings. The value MUST be a float. The default value SHALL be `3.5`.

#### Scenario: REVIEW_MIN_SCORE set to 3.0
- **WHEN** `REVIEW_MIN_SCORE=3.0` is configured in `.env`
- **THEN** only posts with `final_score >= 3.0` SHALL be transitioned to `queued` status and receive translation, Threads draft, and review items

#### Scenario: REVIEW_MIN_SCORE not set
- **WHEN** the `REVIEW_MIN_SCORE` variable is absent from `.env`
- **THEN** the system SHALL default to `3.5`

### Requirement: Auto-publish minimum score threshold from environment variable
The system SHALL read the minimum score threshold for semi-auto publishing from the `AUTO_PUBLISH_MIN_SCORE` environment variable in Settings. The value MUST be a float. The default value SHALL be `4.0`.

#### Scenario: AUTO_PUBLISH_MIN_SCORE set to 3.6
- **WHEN** `AUTO_PUBLISH_MIN_SCORE=3.6` is configured in `.env`
- **THEN** the semi-auto publish path SHALL only auto-approve posts with `final_score >= 3.6`

#### Scenario: AUTO_PUBLISH_MIN_SCORE not set
- **WHEN** the `AUTO_PUBLISH_MIN_SCORE` variable is absent from `.env`
- **THEN** the system SHALL default to `4.0`

### Requirement: Low-score posts are directly archived
Posts with `final_score < REVIEW_MIN_SCORE` SHALL be transitioned from `scored` to `archived` status immediately after scoring. The full `raw_content`, `top_comments_snapshot`, and `score_card` SHALL be retained. No `review_item` SHALL be created for these posts.

#### Scenario: Post scores below threshold
- **WHEN** `IngestionWorker` scores a post and `final_score` is `3.2` while `REVIEW_MIN_SCORE` is `3.5`
- **THEN** the candidate's status SHALL transition `seen → scored → archived`, the full `raw_content` SHALL be stored, a `score_card` SHALL be created, and no `review_item` SHALL be created

#### Scenario: Post scores at or above threshold
- **WHEN** `IngestionWorker` scores a post and `final_score` is `3.5` while `REVIEW_MIN_SCORE` is `3.5`
- **THEN** the candidate SHALL follow the normal pipeline: `seen → scored → queued`, and the `ReviewWorker` SHALL create a `review_item` with translation and Threads draft

#### Scenario: Archived low-score post maintains dedup
- **WHEN** a low-score post has been archived with full `raw_content`
- **THEN** the next ingestion cycle SHALL still detect it via `source_url` dedup (exact match) and semantic dedup (Jaccard similarity), preventing re-ingestion

### Requirement: SCORED to ARCHIVED lifecycle transition
The lifecycle state machine SHALL allow the transition `SCORED → ARCHIVED`. This transition is used for low-score posts that do not qualify for the review queue.

#### Scenario: Valid SCORED to ARCHIVED transition
- **WHEN** a candidate post in `scored` status is transitioned to `archived`
- **THEN** the transition SHALL succeed without raising an assertion error

#### Scenario: Score threshold determines lifecycle path
- **WHEN** a post is scored
- **THEN** the system SHALL route it to one of two paths: `scored → queued` (if `final_score >= REVIEW_MIN_SCORE`) or `scored → archived` (if `final_score < REVIEW_MIN_SCORE`)

### Requirement: Threads draft generation uses REVIEW_MIN_SCORE
The `ReviewPayloadService` SHALL use the `REVIEW_MIN_SCORE` setting as the threshold for generating Threads drafts, replacing the previously hardcoded `3.5` value. Since only posts meeting this threshold enter the review queue, all review items SHALL have draft generation attempted.

#### Scenario: Draft generation threshold matches review threshold
- **WHEN** `REVIEW_MIN_SCORE=3.3` is configured
- **THEN** `ReviewPayloadService` SHALL generate Threads drafts for posts with `final_score >= 3.3`
