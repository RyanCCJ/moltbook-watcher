## 1. Configuration and Environment

- [x] 1.1 Add Telegram settings to `src/config/settings.py`: `telegram_bot_token` (str, default `""`), `telegram_chat_id` (str, default `""`), `telegram_webhook_url` (str, default `""`), `telegram_daily_summary_hour` (int, default `22`), `telegram_daily_summary_timezone` (str, default `"UTC"`)
- [x] 1.2 Add Telegram env vars to `.env.example` with comments explaining each variable
- [x] 1.3 Add a `telegram_enabled` computed property to `Settings` that returns `True` when `telegram_bot_token` is non-empty

## 2. Telegram API Client

- [x] 2.1 Create `src/integrations/telegram_client.py` with a `TelegramClient` class using `httpx.AsyncClient` internally
- [x] 2.2 Implement `set_webhook(url, secret_token)` method calling Telegram `setWebhook` API
- [x] 2.3 Implement `send_message(chat_id, text, reply_markup=None)` method with HTML parse mode support
- [x] 2.4 Implement `edit_message_text(chat_id, message_id, text, reply_markup=None)` method
- [x] 2.5 Implement `answer_callback_query(callback_query_id, text=None)` method
- [x] 2.6 Implement `delete_webhook()` method
- [x] 2.7 Add error handling: log non-2xx responses with method name, status code, and response body; raise an exception on failure
- [x] 2.8 Add `close()` method to cleanly shut down the httpx client
- [x] 2.9 Write unit tests for `TelegramClient` with mocked httpx responses

## 3. TelegramNotificationClient

- [x] 3.1 Add `TelegramNotificationClient` class to `src/integrations/notification_client.py` implementing `NotificationClient` ABC
- [x] 3.2 Implement `send_notification(subject, body)` using the `TelegramClient.send_message` method
- [x] 3.3 Write unit tests verifying notification sends a Telegram message with subject and body

## 4. Telegram Service Layer

- [x] 4.1 Create `src/services/telegram_service.py` with a `TelegramService` class that takes a `TelegramClient` and `chat_id`
- [x] 4.2 Implement `format_review_message(review_item_data)` that formats a review item dict (from the review API response format) into an HTML Telegram message with threads draft (or fallback), score, risk tags, and source URL
- [x] 4.3 Implement content truncation: truncate text to 800 chars with `… (full content omitted)` suffix; ensure total message stays under 4096 chars
- [x] 4.4 Implement `build_review_inline_keyboard(review_item_id)` returning an inline keyboard with Approve, Reject, Reject+Comment, and Edit Draft buttons using `action:id` callback data format
- [x] 4.5 Implement `push_pending_items(items)` that sends one message per item with inline keyboard
- [x] 4.6 Implement `update_message_with_decision(chat_id, message_id, original_text, decision, timestamp, comment=None)` that edits the original message to append the decision result and removes the inline keyboard
- [x] 4.7 Implement in-memory conversation state: `_pending_comments: dict[int, str]` and `_pending_edits: dict[int, str]` keyed by chat_id, with methods to set, get, and clear state
- [x] 4.8 Implement `format_pending_list(items)` for the `/pending` command — compact numbered list with truncated title, score, and risk
- [x] 4.9 Implement `format_stats_message(stats_data)` for the `/stats` command and daily summary
- [x] 4.10 Implement `format_health_message(health_data)` for the `/health` command
- [x] 4.11 Implement `format_help_message()` returning a static help text listing all commands
- [x] 4.12 Write unit tests for message formatting, truncation, keyboard building, and state management

## 5. Webhook Route and Update Handling

- [x] 5.1 Create `src/api/telegram_routes.py` with a FastAPI router
- [x] 5.2 Implement `POST /telegram/webhook` route that verifies `X-Telegram-Bot-Api-Secret-Token` header, returns 403 on mismatch
- [x] 5.3 Add chat ID authorization check: silently return 200 for updates from non-matching chat IDs
- [x] 5.4 Implement callback query dispatcher: parse `action:id` from callback data and route to approve, reject, comment-initiate, or edit-initiate handlers
- [x] 5.5 Implement approve callback handler: call `ReviewItemRepository.decide()` with decision `approved` and `reviewedBy` `telegram`, edit original message, answer callback query
- [x] 5.6 Implement reject callback handler: call `ReviewItemRepository.decide()` with decision `rejected`, edit original message, answer callback query
- [x] 5.7 Implement comment-initiate callback handler: store review item ID in `_pending_comments` state, reply with prompt, answer callback query
- [x] 5.8 Implement edit-initiate callback handler: store review item ID in `_pending_edits` state, reply with prompt, answer callback query
- [x] 5.9 Implement message dispatcher for plain text: check for pending comment state → submit rejection with comment; check for pending edit state → update draft; otherwise treat as command or unknown
- [x] 5.10 Implement command router: dispatch `/pending`, `/ingest`, `/publish`, `/stats`, `/health`, `/help`, `/cancel` to their respective handlers
- [x] 5.11 Implement `/pending` handler: query `ReviewItemRepository.list()` with status `pending`, format with `TelegramService`, send response
- [x] 5.12 Implement `/ingest` handler: reply immediately with "Ingestion started…", run `run_ingestion_once()` as `asyncio.create_task`, send follow-up with metrics or error on completion
- [x] 5.13 Implement `/publish` handler: reply immediately with "Publish cycle started…", run `run_publish_once()` as `asyncio.create_task`, send follow-up with metrics on completion
- [x] 5.14 Implement `/stats` handler: query pending/approved/rejected/published counts, top scoring pending items, format and send
- [x] 5.15 Implement `/health` handler: call health check logic (db + queue), format and send
- [x] 5.16 Implement `/help` handler: send static help message
- [x] 5.17 Implement `/cancel` handler: clear any pending state, reply with confirmation or "Nothing to cancel"
- [x] 5.18 Implement unknown message handler: reply with "Unknown command. Use /help to see available commands."
- [x] 5.19 Handle already-decided items gracefully: if approve/reject is attempted on an already-decided item, answer callback with error text
- [x] 5.20 Ensure all exceptions in update handling are caught and logged, always returning HTTP 200 to Telegram
- [x] 5.21 Write unit tests for webhook route, callback dispatching, command handlers, and state transitions

## 6. Draft Update API Endpoint

- [x] 6.1 Add `PATCH /review-items/{review_item_id}/draft` endpoint to `src/api/review_routes.py`
- [x] 6.2 Accept JSON body: `{"threadsDraft": "new text"}`
- [x] 6.3 Return 404 if review item not found, 409 if already decided
- [x] 6.4 Update `threads_draft` column and return `{"reviewItemId": "<id>", "updated": true}`
- [x] 6.5 Write unit tests for PATCH endpoint (success, not found, already decided)

## 7. App Integration

- [x] 7.1 In `src/api/app.py`: conditionally include the Telegram router when `settings.telegram_enabled` is `True`
- [x] 7.2 In `src/api/app.py`: add startup event to create `TelegramClient`, store on `app.state`, and call `set_webhook`
- [x] 7.3 In `src/api/app.py`: add shutdown event to call `TelegramClient.close()`
- [x] 7.4 In `src/workers/runtime.py`: after review worker cycle in `run_ingestion_once()`, query newly created pending items and push to Telegram via `TelegramService` (skip if Telegram not configured)
- [x] 7.5 In `src/workers/runtime.py`: in `run_publish_once()`, use `TelegramNotificationClient` instead of `SMTPNotificationClient` when Telegram is configured
- [x] 7.6 In `src/workers/scheduler.py`: add a daily summary cron job using `TELEGRAM_DAILY_SUMMARY_HOUR` and `TELEGRAM_DAILY_SUMMARY_TIMEZONE` settings; skip if Telegram not configured

## 8. Documentation

- [x] 8.1 Create `docs/telegram-setup.md` with step-by-step BotFather registration instructions
- [x] 8.2 Add section on discovering your Telegram chat ID (message the bot, call getUpdates)
- [x] 8.3 Add section on environment variable configuration with example `.env` block
- [x] 8.4 Add section on HTTPS and port requirements (Telegram only supports 443, 80, 88, 8443) with guidance on reverse proxy setup or uvicorn TLS configuration
- [x] 8.5 Add verification steps: how to confirm the bot is working (send `/health`, check webhook status)
- [x] 8.6 Add troubleshooting section covering common issues (webhook not registered, bot not responding, permission errors)

## 9. Integration Testing

- [x] 9.1 Write an integration test for the full approve flow: push notification → tap approve → verify decision persisted and message edited
- [x] 9.2 Write an integration test for the reject+comment flow: push notification → tap comment → send comment text → verify rejection with comment
- [x] 9.3 Write an integration test for the edit draft flow: tap edit → send new draft → verify threads_draft updated
- [x] 9.4 Write an integration test for `/ingest` command: verify background task starts and follow-up message is sent
- [x] 9.5 Verify graceful degradation: all features disabled when `TELEGRAM_BOT_TOKEN` is empty

## 10. Telegram Review UX Follow-up

- [x] 10.1 Update `/pending` summary formatting to prefer the first complete sentence instead of a single truncated line
- [x] 10.2 Add `/review <number>` command that opens full review details for a pending item
- [x] 10.3 Format `/review <number>` output as a readable multi-message sequence including original draft, translated draft, original comments, translated comments, and Threads draft last
- [x] 10.4 Update `/help` text to include `/review <number>`
- [x] 10.5 Update tests and OpenSpec documents for the new review-reading flow
- [x] 10.6 Replace local ingestion `window` filtering with direct upstream `time` parameters (`hour`, `day`, `week`, `month`, `all`) across runtime, Telegram, ops API, CLI, and docs
- [x] 10.7 Rename `candidate_posts.source_window` to `source_time` and add migration coverage for existing test databases
- [x] 10.8 Add flexible Telegram `/ingest` parsing so `time`, `sort`, and `limit` tokens can be supplied in any order
