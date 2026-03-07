## Purpose

Provides telegram integration for telegram-bot.

## Requirements

### Requirement: Telegram Bot API client
The system SHALL provide a thin HTTP client wrapping the Telegram Bot API using the existing `httpx` dependency. The client SHALL support the following Telegram API methods: `setWebhook`, `deleteWebhook`, `sendMessage` (with inline keyboard and HTML parse mode), `editMessageText`, and `answerCallbackQuery`.

#### Scenario: Send message with inline keyboard
- **WHEN** the system calls the Telegram client to send a message with inline keyboard buttons
- **THEN** the client SHALL POST to `https://api.telegram.org/bot<token>/sendMessage` with the chat ID, text, `parse_mode: "HTML"`, and a `reply_markup` containing the inline keyboard definition

#### Scenario: Edit existing message
- **WHEN** the system calls the client to edit a previously sent message
- **THEN** the client SHALL POST to `https://api.telegram.org/bot<token>/editMessageText` with the chat ID, message ID, and updated text

#### Scenario: Answer callback query
- **WHEN** the system receives a callback query from an inline button press
- **THEN** the client SHALL POST to `https://api.telegram.org/bot<token>/answerCallbackQuery` with the callback query ID to acknowledge receipt

#### Scenario: API call failure
- **WHEN** a Telegram API call returns a non-2xx status code
- **THEN** the client SHALL log the error with the method name, status code, and response body, and raise an exception

### Requirement: Webhook endpoint
The system SHALL expose a `POST /telegram/webhook` FastAPI route that receives Telegram Update objects as JSON. The route SHALL always return HTTP 200 to Telegram (to prevent retries) and process the update asynchronously if needed.

#### Scenario: Receive valid update
- **WHEN** Telegram sends a POST request to `/telegram/webhook` with a valid Update JSON body
- **THEN** the route SHALL parse the update, dispatch it to the appropriate handler (message or callback_query), and return HTTP 200

#### Scenario: Receive malformed update
- **WHEN** Telegram sends a POST request with a body that cannot be parsed
- **THEN** the route SHALL log the error and return HTTP 200 (to avoid Telegram retries)

### Requirement: Webhook auto-registration
The system SHALL automatically register the Telegram webhook on FastAPI startup by calling the `setWebhook` API with the URL from `TELEGRAM_WEBHOOK_URL` and the secret token derived from `TELEGRAM_BOT_TOKEN`. If `TELEGRAM_BOT_TOKEN` is empty or unset, the system SHALL skip registration and disable all Telegram features gracefully.

#### Scenario: Server startup with valid token
- **WHEN** the FastAPI server starts and `TELEGRAM_BOT_TOKEN` is configured
- **THEN** the system SHALL call `setWebhook` with `url` set to `TELEGRAM_WEBHOOK_URL` and `secret_token` set to a deterministic hash of the bot token

#### Scenario: Server startup without token
- **WHEN** the FastAPI server starts and `TELEGRAM_BOT_TOKEN` is empty
- **THEN** the system SHALL skip webhook registration and NOT mount the Telegram webhook route

### Requirement: Webhook secret verification
The system SHALL verify the `X-Telegram-Bot-Api-Secret-Token` header on every incoming webhook request against the expected secret token. Requests with a missing or mismatched header SHALL be rejected.

#### Scenario: Valid secret token
- **WHEN** a webhook request arrives with the correct `X-Telegram-Bot-Api-Secret-Token` header
- **THEN** the system SHALL process the update normally

#### Scenario: Invalid or missing secret token
- **WHEN** a webhook request arrives with a missing or incorrect secret token header
- **THEN** the system SHALL return HTTP 403 and NOT process the update

### Requirement: Chat ID authorization
The system SHALL only process Telegram updates originating from the chat ID configured in `TELEGRAM_CHAT_ID`. Updates from any other chat ID SHALL be silently ignored (return HTTP 200 with no action).

#### Scenario: Message from authorized chat
- **WHEN** an update arrives from the configured `TELEGRAM_CHAT_ID`
- **THEN** the system SHALL process the update

#### Scenario: Message from unauthorized chat
- **WHEN** an update arrives from a chat ID that does not match `TELEGRAM_CHAT_ID`
- **THEN** the system SHALL ignore the update and return HTTP 200

### Requirement: Environment configuration
The system SHALL read the following environment variables for Telegram configuration:
- `TELEGRAM_BOT_TOKEN`: Bot API token from BotFather (required to enable Telegram features)
- `TELEGRAM_CHAT_ID`: Authorized chat ID for the operator
- `TELEGRAM_WEBHOOK_URL`: Full HTTPS URL for the webhook endpoint
- `TELEGRAM_DAILY_SUMMARY_HOUR`: Hour of day (0-23) for the daily summary push (default: `22`)
- `TELEGRAM_DAILY_SUMMARY_TIMEZONE`: IANA timezone string for the daily summary (default: `UTC`)

#### Scenario: All Telegram env vars configured
- **WHEN** all five Telegram environment variables are set
- **THEN** the system SHALL enable Telegram features including webhook, notifications, and daily summary

#### Scenario: Only bot token missing
- **WHEN** `TELEGRAM_BOT_TOKEN` is empty or unset
- **THEN** the system SHALL disable all Telegram features and operate normally without them

#### Scenario: Daily summary defaults
- **WHEN** `TELEGRAM_DAILY_SUMMARY_HOUR` or `TELEGRAM_DAILY_SUMMARY_TIMEZONE` are not set
- **THEN** the system SHALL default to hour `22` and timezone `UTC`

### Requirement: TelegramNotificationClient
The system SHALL provide a `TelegramNotificationClient` class implementing the existing `NotificationClient` ABC. It SHALL send notifications as Telegram messages to the configured chat ID. When `TELEGRAM_BOT_TOKEN` is configured, `runtime.py` SHALL use this client instead of `SMTPNotificationClient` for the `NotificationService`.

#### Scenario: Terminal publish failure notification via Telegram
- **WHEN** a publish job fails terminally and `TELEGRAM_BOT_TOKEN` is configured
- **THEN** the `NotificationService` SHALL send the failure notification as a Telegram message to the operator

#### Scenario: Fallback to SMTP when Telegram is not configured
- **WHEN** a publish job fails terminally and `TELEGRAM_BOT_TOKEN` is not configured
- **THEN** the `NotificationService` SHALL use the existing `SMTPNotificationClient`

### Requirement: Message formatting
The system SHALL format Telegram messages using HTML parse mode. Long content (threads draft, translated content) SHALL be truncated to 800 characters with a `… (full content omitted)` suffix when exceeding that limit. The total message length SHALL NOT exceed Telegram's 4096 character limit.

#### Scenario: Short content
- **WHEN** a review item's threads draft is 500 characters
- **THEN** the message SHALL include the full draft text without truncation

#### Scenario: Long content truncation
- **WHEN** a review item's threads draft exceeds 800 characters
- **THEN** the message SHALL truncate the draft to 800 characters and append `… (full content omitted)`
