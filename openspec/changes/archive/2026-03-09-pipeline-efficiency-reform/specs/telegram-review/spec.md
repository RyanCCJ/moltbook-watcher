## MODIFIED Requirements

### Requirement: Push notification for new pending items
The system SHALL NOT automatically send individual Telegram messages for each new review item after an ingestion cycle. Instead, the system SHALL send a single ingestion digest summary (defined in `ingestion-digest-notification` capability). The operator SHALL use `/pending` to view and act on individual pending review items on demand.

#### Scenario: Ingestion cycle completes with new review items
- **WHEN** the ingestion cycle creates new review items
- **THEN** the system SHALL send a single digest summary message instead of individual per-item notifications

#### Scenario: Operator reviews pending items
- **WHEN** the operator sends `/pending` via Telegram
- **THEN** the system SHALL display individual pending review items with inline action buttons (Approve, Reject, Reject+Comment, Edit Draft), same as before
