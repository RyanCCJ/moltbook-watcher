## Why

The current review workflow requires terminal access to the CLI (`scripts/ops_cli.py`) and a connection to the API server. This is impractical when away from the workstation. A Telegram Bot integration would provide a mobile-friendly interface for reviewing pending items, approving/rejecting drafts, triggering operational commands, and receiving push notifications — all from a phone.

## What Changes

- Add a Telegram Bot API client (`httpx`-based, no new dependencies) for sending messages, inline keyboards, and handling callback queries.
- Add a FastAPI webhook endpoint (`/telegram/webhook`) to receive Telegram updates — fits directly into the existing server process with zero additional deployment overhead.
- Implement interactive review via inline keyboard buttons (Approve / Reject / Reject+Comment) that call the existing review decision API internally.
- Push notifications for new pending review items after each review worker cycle.
- Bot commands for operational control from mobile: `/pending`, `/ingest`, `/publish`, `/stats`, `/health`, `/help`.
- Scheduled daily summary push at a configurable hour/timezone (via env vars) with pending/approved/published counts.
- Add `TelegramNotificationClient` implementing the existing `NotificationClient` ABC, supplementing or replacing SMTP for failure alerts.
- Support draft editing from Telegram (reply with new text to update a review item's threads_draft).

## Capabilities

### New Capabilities
- `telegram-bot`: Core Telegram Bot integration — client, webhook handler, message formatting, inline keyboard interactions, and security (webhook secret + chat ID whitelist).
- `telegram-review`: Interactive review flow via Telegram — push pending items with inline approve/reject buttons, comment collection on reject, draft editing via reply.
- `telegram-commands`: Bot command handlers for operational control — `/pending`, `/ingest`, `/publish`, `/stats`, `/health`, `/help`, and scheduled daily summary.

### Modified Capabilities
- (none — existing specs are unaffected; we consume existing APIs internally)

## Impact

- **New files**: `src/integrations/telegram_client.py`, `src/services/telegram_service.py`, `src/api/telegram_routes.py`
- **Modified files**: `src/config/settings.py` (5 new env vars), `src/api/app.py` (router + startup hook), `src/workers/runtime.py` (post-review notification), `src/workers/scheduler.py` (daily summary job), `src/integrations/notification_client.py` (new subclass), `.env.example`
- **Documentation**: New `docs/telegram-setup.md` with BotFather registration, chat ID discovery, env configuration, and HTTPS/port setup guide
- **Dependencies**: None — uses existing `httpx`
- **APIs**: New `POST /telegram/webhook` endpoint; optional new `PATCH /review-items/{id}/draft` for editing
- **Deployment**: No additional processes; webhook runs inside existing FastAPI server. Tailscale DNS provides network-level access control.
