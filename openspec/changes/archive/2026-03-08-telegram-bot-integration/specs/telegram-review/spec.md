## ADDED Requirements

### Requirement: Push notification for new pending items
The system SHALL send a Telegram message to the operator for each new review item created during a review worker cycle. The message SHALL include the threads draft (or translated content as fallback, or english draft as second fallback), the final AI score, risk tags, source URL, and inline action buttons.

#### Scenario: New review item created with threads draft
- **WHEN** the review worker cycle creates a new review item that has a non-empty threads draft
- **THEN** the system SHALL send a Telegram message displaying the threads draft, final score, risk tags, and source URL, with inline buttons for Approve, Reject, and Reject+Comment

#### Scenario: New review item without threads draft
- **WHEN** the review worker cycle creates a new review item with an empty threads draft
- **THEN** the system SHALL fall back to displaying the translated content, or english draft if translated content is also empty

#### Scenario: No new review items
- **WHEN** the review worker cycle creates zero new review items
- **THEN** the system SHALL NOT send any Telegram notification

### Requirement: Approve via inline button
The system SHALL allow the operator to approve a review item by tapping the Approve inline keyboard button. The callback data SHALL use the format `approve:<review_item_id>`. Upon receiving this callback, the system SHALL call the review decision logic with decision `approved` and `reviewedBy` set to `telegram`, then edit the original message to reflect the approval.

#### Scenario: Tap approve button
- **WHEN** the operator taps the `✅ Approve` button on a pending review item message
- **THEN** the system SHALL approve the review item, answer the callback query, and edit the original message to append an approval confirmation with timestamp

#### Scenario: Approve already-decided item
- **WHEN** the operator taps Approve on an item that has already been decided
- **THEN** the system SHALL answer the callback query with an error message indicating the item was already decided

### Requirement: Reject via inline button
The system SHALL allow the operator to reject a review item by tapping the Reject inline keyboard button. The callback data SHALL use the format `reject:<review_item_id>`. Upon receiving this callback, the system SHALL call the review decision logic with decision `rejected`, `reviewedBy` set to `telegram`, and no comment.

#### Scenario: Tap reject button
- **WHEN** the operator taps the `❌ Reject` button on a pending review item message
- **THEN** the system SHALL reject the review item, answer the callback query, and edit the original message to append a rejection confirmation with timestamp

### Requirement: Reject with comment
The system SHALL allow the operator to reject a review item with a comment by tapping the Reject+Comment inline keyboard button. The callback data SHALL use the format `comment:<review_item_id>`. The system SHALL enter a comment-collection state, sending a prompt message asking the operator to type their comment. The next plain text message from the operator SHALL be treated as the rejection comment.

#### Scenario: Tap reject+comment and provide comment
- **WHEN** the operator taps the `💬 Reject + Comment` button
- **THEN** the system SHALL reply with "Please type your rejection comment:"
- **WHEN** the operator sends a plain text message while in comment-collection state
- **THEN** the system SHALL reject the review item with the provided comment, edit the original message to show the rejection and comment, and exit comment-collection state

#### Scenario: Cancel comment collection
- **WHEN** the operator is in comment-collection state and sends `/cancel`
- **THEN** the system SHALL exit comment-collection state, reply with a cancellation confirmation, and leave the review item unchanged

### Requirement: Edit threads draft
The system SHALL allow the operator to edit a review item's threads draft by tapping the Edit inline keyboard button. The callback data SHALL use the format `edit:<review_item_id>`. The system SHALL enter an edit-collection state, sending a prompt asking the operator to type the new draft. The next plain text message SHALL be treated as the new threads draft and persisted via a `PATCH /review-items/{id}/draft` endpoint.

#### Scenario: Edit draft successfully
- **WHEN** the operator taps the `✏️ Edit Draft` button on a pending review item
- **THEN** the system SHALL reply with "Send me the new draft text:"
- **WHEN** the operator sends a plain text message while in edit-collection state
- **THEN** the system SHALL update the review item's threads_draft field, confirm the update, and exit edit-collection state

#### Scenario: Cancel edit
- **WHEN** the operator is in edit-collection state and sends `/cancel`
- **THEN** the system SHALL exit edit-collection state and reply with a cancellation confirmation

### Requirement: Draft update API endpoint
The system SHALL expose a `PATCH /review-items/{review_item_id}/draft` endpoint that accepts a JSON body with a `threadsDraft` string field. It SHALL update the review item's `threads_draft` column and return the updated review item ID.

#### Scenario: Update draft for existing pending item
- **WHEN** a PATCH request is sent with a valid review item ID and non-empty `threadsDraft`
- **THEN** the system SHALL update the threads_draft field and return `{"reviewItemId": "<id>", "updated": true}`

#### Scenario: Update draft for non-existent item
- **WHEN** a PATCH request is sent with a review item ID that does not exist
- **THEN** the system SHALL return HTTP 404

#### Scenario: Update draft for already-decided item
- **WHEN** a PATCH request is sent for a review item that has already been approved or rejected
- **THEN** the system SHALL return HTTP 409 with an error indicating the item is already decided

### Requirement: Callback data encoding
The system SHALL encode inline keyboard callback data in the format `<action>:<review_item_id>` where action is one of `approve`, `reject`, `comment`, or `edit`. The total callback data length SHALL NOT exceed 64 bytes.

#### Scenario: Valid callback data
- **WHEN** the system generates callback data for a review item with a UUID identifier
- **THEN** the callback data SHALL be in the format `approve:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` and SHALL be at most 64 bytes

### Requirement: Conversation state management
The system SHALL maintain in-memory state for pending comment and edit interactions using dictionaries keyed by chat ID. Only one pending interaction (comment or edit) SHALL be active per chat at a time. Starting a new interaction SHALL cancel any previous pending interaction for that chat.

#### Scenario: Overlapping interactions
- **WHEN** the operator taps Reject+Comment on item A, then taps Edit on item B before sending a comment
- **THEN** the comment-collection state for item A SHALL be cancelled, and the system SHALL enter edit-collection state for item B
