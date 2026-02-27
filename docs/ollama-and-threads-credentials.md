# Ollama Setup and Threads API Credentials Guide

This document explains:
- how to start/configure Ollama for this project
- how to obtain `THREADS_API_TOKEN` and `THREADS_ACCOUNT_ID` (user ID)

---

## 1. Ollama: Install, Start, and Configure

### 1.1 Install Ollama

Follow the official install docs:
- https://docs.ollama.com/

Linux quick install (official):

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 1.2 Start Ollama service

```bash
ollama serve
```

By default, Ollama serves API at:
- `http://localhost:11434/api`

### 1.3 Pull the model used by this project

This project defaults to:
- `OLLAMA_MODEL=qwen3:4b`

Pull it:

```bash
ollama pull qwen3:4b
```

### 1.4 Verify Ollama is working

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "qwen3:4b",
  "prompt": "Say hello in one sentence.",
  "stream": false,
  "think": false
}'
```

Validation rule for this project:
- Use only `response` as model output.
- Do not consume `thinking` tokens as final content.

Quick check:
- `response` should be non-empty text.
- if `response` is empty, treat that call as invalid and fallback/retry.

### 1.5 Configure this project

Set in `.env`:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:4b
```

---

## 2. Threads API: Get `THREADS_API_TOKEN` and `THREADS_ACCOUNT_ID`

The recommended references:
- Meta Threads official Postman collection (verified publisher: Meta):
  - https://www.postman.com/meta/threads/collection/dht3nzz/threads-api
- Meta sample repo:
  - https://github.com/fbsamples/threads_api

### 2.1 Create a Threads app in Meta

In Meta Developer Dashboard:
1. Create/select your app with the **Threads use case**.
2. Use the **Threads App ID / Threads App Secret** (not the regular app credentials).

From Meta sample notes:
- Threads app credentials are separate from regular app credentials.

### 2.2 Configure OAuth redirect URI correctly

Important constraints from Meta sample:
- Redirect URI must be configured in app dashboard.
- For local testing, `localhost` redirect is not supported in their sample flow.
- Use HTTPS domain callback (example from sample: `https://threads-sample.meta:8000/callback`).

### 2.3 Exchange authorization code for short-lived user token

Use Meta Postman flow or direct API:

```bash
curl -X POST "https://graph.threads.net/oauth/access_token?client_id=<THREADS_APP_ID>&client_secret=<THREADS_APP_SECRET>&code=<AUTH_CODE>&grant_type=authorization_code&redirect_uri=<REDIRECT_URI>"
```

Expected response shape (from Meta Postman docs):

```json
{
  "access_token": "string",
  "user_id": "string"
}
```

- `access_token` => your short-lived user token
- `user_id` => your Threads account ID (can be used as `THREADS_ACCOUNT_ID`)

### 2.4 Exchange to long-lived token (recommended)

```bash
curl -G "https://graph.threads.net/access_token" \
  --data-urlencode "grant_type=th_exchange_token" \
  --data-urlencode "client_secret=<THREADS_APP_SECRET>" \
  --data-urlencode "access_token=<SHORT_LIVED_USER_TOKEN>"
```

Response includes:
- `access_token` (long-lived token)
- `expires_in`

Use this long-lived token for `THREADS_API_TOKEN`.

### 2.5 (Optional) Get account ID again via profile endpoint

Meta Postman profile request uses:
- `GET https://graph.threads.net/me?fields=id,username,...`

Example:

```bash
curl -G "https://graph.threads.net/me" \
  --data-urlencode "fields=id,username" \
  --data-urlencode "access_token=<THREADS_API_TOKEN>"
```

Use returned `id` as `THREADS_ACCOUNT_ID`.

### 2.6 Configure this project

Put final values in `.env`:

```env
THREADS_API_BASE_URL=https://graph.threads.net
THREADS_API_TOKEN=<LONG_LIVED_USER_ACCESS_TOKEN>
THREADS_ACCOUNT_ID=<THREADS_USER_ID>
```

---

## 3. Quick Validation in This Project

After `.env` is ready:

1. Initialize schema

```bash
uv run python scripts/migrate.py
```

2. Start API and worker

```bash
make api
make worker
```

3. Check health

```bash
curl http://127.0.0.1:8000/health
```

---

## 4. Security Notes

- Never commit `.env` with real tokens/secrets.
- Rotate Threads tokens if exposed.
- Keep `THREADS_APP_SECRET`, `THREADS_API_TOKEN`, and SMTP secrets in secret manager for production.
