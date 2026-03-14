# Telegram Bot Setup

## 1. Register the bot with BotFather

1. Open Telegram and start a chat with `@BotFather`.
2. Send `/newbot`.
3. Follow the prompts to choose a display name and a unique bot username ending in `bot`.
4. Copy the Bot API token that BotFather returns. You will use it as `TELEGRAM_BOT_TOKEN`.
5. Optional but useful: run `/setdescription`, `/setabouttext`, and `/setuserpic` in BotFather so the bot is recognizable on mobile.

## 2. Find your chat ID

1. Start a direct chat with your bot and send any message, for example `/start`.
2. This step matters: `getUpdates` will usually not show a usable `message.chat.id` until the bot has received at least one message from you.
3. Call Telegram `getUpdates` with your bot token:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates"
```

4. Look for `message.chat.id` in the JSON response.
5. Copy that numeric value into `TELEGRAM_CHAT_ID`.

## 3. Configure the environment

Add the Telegram settings to your `.env` file:

```env
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_CHAT_ID=123456789
TELEGRAM_WEBHOOK_URL=https://your-host.example/telegram/webhook
TELEGRAM_DAILY_SUMMARY_HOUR=22
TELEGRAM_DAILY_SUMMARY_TIMEZONE=Asia/Taipei
```

Variable reference:

- `TELEGRAM_BOT_TOKEN`: BotFather token. Leave empty to disable Telegram features.
- `TELEGRAM_CHAT_ID`: Single authorized operator chat ID.
- `TELEGRAM_WEBHOOK_URL`: Full HTTPS URL that Telegram will call.
- `TELEGRAM_DAILY_SUMMARY_HOUR`: Hour of day for the daily summary, `0-23`.
- `TELEGRAM_DAILY_SUMMARY_TIMEZONE`: IANA timezone, for example `UTC` or `Asia/Taipei`.

## 4. HTTPS and port requirements

Telegram webhooks require HTTPS and only support ports `443`, `80`, `88`, or `8443`.

You have three common deployment options:

1. Reverse proxy in front of Uvicorn

Use Caddy, Nginx, or another TLS terminator on port `443` or `8443`, then proxy `/telegram/webhook` to the FastAPI app.

2. Direct Uvicorn TLS

Run Uvicorn with certificate and key files on a supported port:

```bash
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8443 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

3. Tailscale Funnel to local Uvicorn

If your API is already running locally on port `8000`, you can keep that setup and let Tailscale provide the public HTTPS endpoint for Telegram.

Start the API:

```bash
make api
```

Start Funnel in the background:

```bash
tailscale funnel --bg 8000
```

Tailscale will print a public HTTPS URL such as:

```text
https://your-machine.your-tailnet.ts.net
```

Set:

```env
TELEGRAM_WEBHOOK_URL=https://your-machine.your-tailnet.ts.net/telegram/webhook
```

In this model, Telegram reaches the Tailscale HTTPS endpoint, and Tailscale forwards the request to your local app on port `8000`. You do not need to change `make api` to port `8443`.

## 5. Verify the bot

1. Start the API server with Telegram variables configured.
2. Confirm the app registers the webhook on startup.
3. Send `/health` to the bot and verify it responds with database and webhook status.
4. Send `/pending`, `/help`, and `/recall` to confirm command routing works.
5. Trigger ingestion if needed:

```text
/ingest
/ingest day
/ingest 20 new month
```

The `/ingest` command accepts `time`, `sort`, and `limit` tokens in any order.
6. Optionally verify webhook status directly:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

7. Verify archive + recall behavior:
   - make sure at least one queued pending item is older than 14 days
   - trigger the summary cycle or wait for the scheduled daily summary
   - confirm the summary includes `Auto-archived: N`
   - send `/recall` and verify eligible high-score archived items are listed
   - press `Recall` and verify the bot replies with `Item recalled.`

## 6. Troubleshooting

### Webhook not registered

- Verify `TELEGRAM_WEBHOOK_URL` is set and reachable from Telegram.
- Confirm the server is listening on `443`, `80`, `88`, or `8443`.
- Check startup logs for Telegram webhook registration errors.
- If using Tailscale Funnel, confirm `tailscale funnel --bg 8000` is still active and that the generated `https://...ts.net` URL matches `TELEGRAM_WEBHOOK_URL`.

### Bot does not respond

- Make sure `TELEGRAM_BOT_TOKEN` is not empty.
- Confirm you sent messages from the chat ID configured in `TELEGRAM_CHAT_ID`.
- If `getUpdates` looks empty, send a message to the bot first, then run `getUpdates` again.
- Verify the webhook secret header matches by restarting the app after updating the token.

### Permission or connectivity errors

- Confirm the database is healthy with `/health`.
- If using a reverse proxy, check that `/telegram/webhook` is forwarded unchanged.
- If using Tailscale or private DNS, confirm the hostname resolves from the public internet if Telegram must reach it directly.

### `/recall` does not show an expected item

- The item must have been archived by `archive-worker`, not manually by an operator.
- The item must still be in `archived` status.
- The item must have `final_score >= 4.0`.
- If it was already recalled once, pressing the button again returns `Item already recalled.`
