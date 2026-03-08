# Capability: Routing Integration

## Purpose
Wire RoutingService into the pipeline and log route decision results on ScoreCards.

## Requirements

### Requirement: RoutingService called after scoring in IngestionWorker
The `IngestionWorker.run_cycle()` SHALL call `RoutingService.route_candidate()` for every scored post, immediately after creating the score_card and before lifecycle transitions.

#### Scenario: Post is routed after scoring
- **WHEN** `IngestionWorker` scores a new post
- **THEN** `RoutingService.route_candidate()` SHALL be called with the post's `final_score` and `risk_score`, and the returned route decision SHALL be stored on the `score_card`

### Requirement: Route decision persisted on score_card
The `score_cards` table SHALL have a `route_decision` column (VARCHAR(32), nullable, default NULL) that stores the routing classification returned by `RoutingService.route_candidate()`. Valid values are `fast_track`, `review_queue`, and `risk_priority`.

#### Scenario: Route decision stored
- **WHEN** a post is scored and routed
- **THEN** the `score_card.route_decision` field SHALL contain the route classification (e.g., `"fast_track"`, `"review_queue"`, or `"risk_priority"`)

#### Scenario: Database migration
- **WHEN** the migration is applied to an existing database
- **THEN** existing score_cards SHALL have `route_decision` set to NULL (existing data was created before routing)

### Requirement: RoutingService thresholds are configurable
The `RoutingService` constructor SHALL accept `fast_track_min_score` and `fast_track_max_risk` parameters that control the routing classification logic, enabling thresholds to be tuned from Settings.

#### Scenario: Custom fast-track thresholds
- **WHEN** `RoutingService` is constructed with `fast_track_min_score=3.6` and `fast_track_max_risk=1`
- **THEN** a post with `final_score=3.7` and `risk_score=1` SHALL be routed as `fast_track`

#### Scenario: Default thresholds
- **WHEN** `RoutingService` is constructed with defaults
- **THEN** the fast-track thresholds SHALL use `AUTO_PUBLISH_MIN_SCORE` and `risk_score <= 1`

### Requirement: Remove is_follow_up_allowed method
The `RoutingService.is_follow_up_allowed()` method SHALL be removed. Follow-up logic is handled by `FollowUpService` which provides a richer `FollowUpEvaluation` dataclass.

#### Scenario: Method removed
- **WHEN** the codebase is searched for `is_follow_up_allowed`
- **THEN** no references to `RoutingService.is_follow_up_allowed` SHALL exist
