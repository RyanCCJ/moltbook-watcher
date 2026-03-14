## ADDED Requirements

### Requirement: /recall command lists recallable items
The system SHALL respond to the `/recall` Telegram command by listing all auto-archived review items that have `final_score >= 4.0` and `reviewed_by == "archive-worker"`. The list SHALL be ordered by `final_score` descending and limited to 10 items. Each item SHALL display a truncated title (first sentence of the English draft or threads draft), the final score, and the source URL. Each item SHALL include an inline keyboard button labeled "Recall" that triggers the unarchive flow.

#### Scenario: Recallable items exist
- **WHEN** the operator sends `/recall` and there are 3 auto-archived items with `final_score >= 4.0`
- **THEN** the system SHALL reply with a numbered list of 3 items, each with title, score, source URL, and a "Recall" inline button

#### Scenario: No recallable items
- **WHEN** the operator sends `/recall` and there are no auto-archived items with `final_score >= 4.0`
- **THEN** the system SHALL reply with "No recallable items."

#### Scenario: More than 10 recallable items
- **WHEN** the operator sends `/recall` and there are 15 eligible items
- **THEN** the system SHALL show only the top 10 by score

#### Scenario: Manually rejected items excluded
- **WHEN** the operator sends `/recall` and there are archived items where `reviewed_by != "archive-worker"` (e.g., manually rejected then archived)
- **THEN** the system SHALL NOT include those items in the recall list

### Requirement: Recall inline button unarchives an item
The system SHALL handle the "Recall" inline keyboard callback by transitioning the candidate post from `ARCHIVED` back to `QUEUED` and resetting the review item's decision to `"pending"`, clearing `reviewed_by` and `reviewed_at`. After a successful recall, the item re-enters the review pipeline as if freshly queued, retaining all original content (drafts, translations, risk tags, scores).

#### Scenario: Successful recall
- **WHEN** the operator presses the "Recall" button for an auto-archived item
- **THEN** the system SHALL transition the candidate post status from `ARCHIVED` to `QUEUED`, reset the review item decision to `"pending"`, clear `reviewed_by` and `reviewed_at`, and reply with a confirmation message

#### Scenario: Item already recalled
- **WHEN** the operator presses "Recall" for an item that has already been recalled (no longer archived)
- **THEN** the system SHALL reply with "Item already recalled." without making changes

#### Scenario: Item not eligible for recall
- **WHEN** the operator presses "Recall" for an item that was not archived by the archive-worker
- **THEN** the system SHALL reply with "This item cannot be recalled." without making changes

### Requirement: Unarchive lifecycle transition
The candidate post lifecycle SHALL allow the transition `ARCHIVED → QUEUED` to support the recall flow. This transition SHALL be the only outgoing transition from the `ARCHIVED` state.

#### Scenario: Valid unarchive transition
- **WHEN** a candidate post is in `ARCHIVED` status and the recall handler triggers a transition to `QUEUED`
- **THEN** the transition SHALL succeed and the candidate post status SHALL become `QUEUED`

#### Scenario: Other transitions from ARCHIVED remain blocked
- **WHEN** code attempts to transition a candidate post from `ARCHIVED` to any state other than `QUEUED` (e.g., `APPROVED`, `PUBLISHED`)
- **THEN** the transition SHALL raise a `ValueError`
