## Context

The moltbook-watcher pipeline currently operates via:
- **FastAPI server** (`src/api/app.py`) with routes for review items, publishing, and ops triggers
- **CLI tool** (`scripts/ops_cli.py`) that calls the API over HTTP
- **Scheduler** (`src/workers/scheduler.py`) using APScheduler for periodic ingestion and publish cycles
- **Notification** via `NotificationClient` ABC with `TelegramNotificationClient` implementation for publish job terminal failures

The server runs on a host reachable via Tailscale DNS. The operator needs mobile access for reviewing and approving content while away from the workstation.

**Current review data available per item** (from `review_routes.py`):
- `draftContent` (english_draft), `translatedContent`, `threadsDraft`
- `topCommentsSnapshot`, `topCommentsTranslated`
- `aiScore` (novelty, depth, tension, reflective_impact, engagement, risk, content, final)
- `riskTags`, `sourceUrl`, `capturedAt`, `followUpRationale`, `decision`

## Goals / Non-Goals

**Goals:**
- Enable full review workflow (view, approve, reject with comment) from Telegram on mobile
- Push new pending items to Telegram automatically after each review worker cycle
- Provide bot commands for operational control (`/pending`, `/review`, `/ingest`, `/publish`, `/stats`, `/health`)
- Send a daily summary at a configurable time/timezone (via env vars) with pipeline statistics
- Support editing Threads drafts via Telegram reply
- Zero new Python dependencies (use existing `httpx`)
- Zero new processes (webhook runs inside existing FastAPI server)

**Non-Goals:**
- Multi-user / group chat support (single operator only)
- Replacing the CLI tool (Telegram supplements it)
- Bot polling mode (webhook only; Tailscale provides reliable reachability)
- Media/image handling in Telegram messages
- Inline query support

## Decisions

### D1: Webhook mode, mounted on existing FastAPI

**Choice**: Register a Telegram webhook pointing to the configured `TELEGRAM_WEBHOOK_URL` (e.g., `https://<your-tailscale-host>:8443/telegram/webhook`) and handle updates inside a new FastAPI route.

**Alternatives considered**:
- *Polling mode*: Requires a separate long-running loop or asyncio task. Adds complexity and a second failure domain. Would be needed if the server had no stable URL — but Tailscale provides one.
- *Separate webhook server*: Unnecessary when FastAPI is already running.

**Rationale**: The server already runs continuously under tmux. Adding one route is ~5 lines of plumbing. Tailscale DNS is stable and private — no port forwarding or public exposure needed.

### D2: Raw httpx instead of python-telegram-bot library

**Choice**: Use `httpx` (already in dependencies) to call Telegram Bot API endpoints directly.

**Alternatives considered**:
- *python-telegram-bot*: Full-featured SDK with update handlers, conversation state, etc. But it pulls in many transitive dependencies and imposes its own dispatcher architecture that conflicts with our FastAPI webhook approach.
- *aiogram*: Similar trade-offs.

**Rationale**: The Telegram Bot API is a simple REST interface. We need ~5 endpoints: `setWebhook`, `sendMessage`, `editMessageText`, `answerCallbackQuery`, `deleteWebhook`. A thin wrapper of ~120 lines is cleaner than importing a framework.

### D3: Callback data encoding for inline buttons

**Choice**: Encode callback data as `action:review_item_id`, e.g., `approve:abc123`, `reject:abc123`, `comment:abc123`, `edit:abc123`. Max 64 bytes per Telegram's limit.

**Alternatives considered**:
- *JSON in callback data*: Wasteful for simple payloads; 64-byte limit makes this fragile.
- *Numeric IDs with a lookup table*: Over-engineering for single-user use.

**Rationale**: Review item IDs are UUIDs (36 chars). With a 7-char prefix (`approve:`), total is 43 bytes — well within the 64-byte limit.

### D4: Conversation state for comment collection

**Choice**: Use a simple in-memory dict (`_pending_comments: dict[int, str]`) mapping `chat_id` to `review_item_id` for the "awaiting comment" state. When the user taps "Reject + Comment", store the review item ID. The next plain text message from that chat is treated as the comment.

**Alternatives considered**:
- *Redis-backed state*: Overkill for single-user; adds unnecessary coupling.
- *Force inline reply*: Telegram inline reply UX is clunky on mobile for entering text.

**Rationale**: Single-user bot means only one state slot is ever active. An in-memory dict is trivially simple and has no persistence overhead. State is lost on restart which is acceptable — the user just taps the button again.

The same pattern applies to the "edit draft" flow: store `_pending_edits: dict[int, str]` mapping chat_id to review_item_id.

### D5: Security model

**Choice**: Three layers:
1. **Tailscale network isolation**: Webhook URL is only reachable within the tailnet.
2. **Webhook secret token**: Set `secret_token` when calling `setWebhook`. Telegram includes it in the `X-Telegram-Bot-Api-Secret-Token` header. The webhook route verifies it.
3. **Chat ID whitelist**: Only process updates from the configured `TELEGRAM_CHAT_ID`. Ignore all others silently.

**Rationale**: Tailscale already provides strong network-level isolation. The webhook secret and chat ID check are defense-in-depth. No API authentication tokens are exposed to Telegram.

### D6: TelegramNotificationClient as NotificationClient subclass

**Choice**: Add `TelegramNotificationClient` implementing the existing `NotificationClient` ABC. Configure it via settings to replace or supplement SMTP.

**Alternatives considered**:
- *Standalone notification function*: Breaks the existing pattern; `NotificationService` expects a `NotificationClient` instance.
- *Multiple clients in NotificationService*: Would require refactoring the service to accept a list of clients. Could be done later but is a non-goal for now.

**Rationale**: Drop-in replacement. `runtime.py` already builds `SMTPNotificationClient` → swap to `TelegramNotificationClient` when `TELEGRAM_BOT_TOKEN` is set. The existing `NotificationService.notify_terminal_failure()` works unchanged.

### D7: Post-review-cycle push notification

**Choice**: After `ReviewWorker.run_cycle()` completes in `runtime.py`, query for newly created pending items and push each to Telegram with inline action buttons.

**Alternatives considered**:
- *Event-driven (Redis pub/sub)*: Overly complex for a synchronous pipeline.
- *Push from ReviewWorker directly*: Would create a dependency from the worker to the Telegram client; violates the current clean separation.

**Rationale**: `runtime.py` already orchestrates worker calls sequentially. Adding a post-cycle notification call there is consistent with the existing pattern (similar to how `run_publish_once` constructs the notification service).

### D8: Message formatting and length

**Choice**: Use Telegram's HTML parse mode for rich formatting. Truncate push-notification review messages when needed, but support a dedicated `/review <number>` command that sends the full review details across multiple Telegram messages. In the detailed view, show original draft, translated draft, original comments, translated comments, and place the Threads draft last so the operator can read through supporting context before reaching the publish text and action buttons.

For `/pending` listing, show a compact summary based on the first complete sentence plus score and risk, with a maximum of 10 items, and let `/review <number>` open the full details.

### D9: Draft editing via PATCH endpoint

**Choice**: Add a `PATCH /review-items/{review_item_id}/draft` endpoint that accepts `{"threadsDraft": "new text"}` and updates the review item's `threads_draft` field. The Telegram edit flow calls this endpoint internally.

**Rationale**: Keeps the Telegram service layer thin — it formats messages and delegates to the API layer, just like the CLI does. The PATCH endpoint is also useful for future web UIs or other integrations.

### D10: Daily summary scheduling

**Choice**: Add a new APScheduler `cron` job in `scheduler.py` that fires at the time configured by `TELEGRAM_DAILY_SUMMARY_HOUR` and `TELEGRAM_DAILY_SUMMARY_TIMEZONE` env vars (e.g., `22` and `Asia/Taipei` → 22:00 local time). It queries pending/approved/rejected/published counts and sends a formatted summary via the Telegram client.

**Rationale**: Reuses the existing scheduler infrastructure. A cron trigger (vs interval) ensures the summary always arrives at the expected local time regardless of server uptime. Making the hour and timezone configurable avoids hardcoding assumptions about the operator's location.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| Telegram API downtime | Push notifications delayed; review still works via CLI | Log failures; operator can retry later from Telegram or CLI |
| Webhook registration lost after Telegram server maintenance | Bot stops receiving updates | Auto-register webhook on every FastAPI startup; add `/health` check for webhook status |
| In-memory conversation state lost on server restart | User needs to re-tap "Reject + Comment" or "Edit" button | Acceptable for single-user; state is ephemeral by design |
| Tailscale DNS becomes unreachable | Webhook endpoint unreachable; no push notifications | Existing CLI still works if SSH is available; monitor Tailscale status |
| Long-running `/ingest` command blocks webhook response | Telegram may retry the webhook | Run ingest as background task (`asyncio.create_task`), respond to Telegram immediately with "Ingestion started…" |
| Message too long for Telegram 4096 char limit | Message fails to send | Truncation logic with configurable max length; split into multiple messages as fallback |

### D11: Ingestion time filter semantics

**Choice**: Remove the local `window` abstraction and pass the upstream Moltbook API `time` parameter directly through the ingestion stack. Supported values are `hour`, `day`, `week`, `month`, and `all`. Telegram `/ingest` uses `time=hour`, `sort=top`, `limit=100` by default. Rename the `candidate_posts` column from `source_window` to `source_time` so persisted metadata matches the new semantics.

**Alternatives considered**:
- *Keep local window filtering*: This caused misleading results because `sort=top` was applied before the local time cutoff, so recent posts could be missed.
- *Support both `window` and `time`*: Adds compatibility glue, but preserves a wrong abstraction and makes the system harder to reason about.

**Rationale**: The upstream API already defines the correct time semantics. Reusing them makes `fetched_count` match operator expectations and removes the fragile local post-filtering logic.

### D12: Flexible Telegram /ingest token parsing

**Choice**: Allow Telegram `/ingest` to accept optional `time`, `sort`, and `limit` tokens in any order, for example `/ingest day`, `/ingest 20 week`, or `/ingest rising month 50`.

**Alternatives considered**:
- *Fixed positional arguments*: Easier to parse, but awkward on mobile because the operator must remember the exact order.
- *Key/value syntax*: More explicit, but too verbose for Telegram chat usage.

**Rationale**: The token vocabulary is small and non-overlapping enough to parse safely. This keeps the command fast to type on mobile while still allowing the operator to override the default ingestion scope when needed.

## Open Questions

- **HTTPS certificate**: Tailscale MagicDNS provides automatic HTTPS certs. Need to verify that the FastAPI/uvicorn instance is configured with TLS, or if a reverse proxy (e.g., Caddy) is needed in front. Telegram webhooks require HTTPS.
- **Webhook port**: Telegram only supports ports 443, 80, 88, or 8443 for webhooks. If the FastAPI server runs on a different port, either reconfigure to 8443 or place a reverse proxy on 443.
- **Setup documentation**: A `docs/telegram-setup.md` guide is needed to walk through BotFather registration, chat ID discovery, env configuration, and HTTPS/port setup.
