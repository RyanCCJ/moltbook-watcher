# Process Supervision Runbook (systemd + launchd)

This guide describes stable long-running operation for:
- API service
- Scheduler/worker service

It replaces terminal-only operation (`make api`, `make worker`) with OS service managers.

## 1. Production Start Commands

Use non-reload commands in long-running mode:

- API:

```bash
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

- Worker:

```bash
uv run python -m src.workers.scheduler
```

Do not use `--reload` in production services.

---

## 2. Linux: systemd

### 2.1 API unit

Create `/etc/systemd/system/moltbook-api.service`:

```ini
[Unit]
Description=Moltbook Watcher API
After=network.target
Wants=network.target

[Service]
Type=simple
User=<YOUR_USER>
WorkingDirectory=<PROJECT_DIR>
EnvironmentFile=<PROJECT_DIR>/.env
ExecStart=/usr/bin/env uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
```

### 2.2 Worker unit

Create `/etc/systemd/system/moltbook-worker.service`:

```ini
[Unit]
Description=Moltbook Watcher Scheduler Worker
After=network.target
Wants=network.target

[Service]
Type=simple
User=<YOUR_USER>
WorkingDirectory=<PROJECT_DIR>
EnvironmentFile=<PROJECT_DIR>/.env
ExecStart=/usr/bin/env uv run python -m src.workers.scheduler
Restart=always
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
```

### 2.3 Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now moltbook-api.service
sudo systemctl enable --now moltbook-worker.service
```

### 2.4 Check status and logs

```bash
systemctl status moltbook-api.service
systemctl status moltbook-worker.service
journalctl -u moltbook-api.service -f
journalctl -u moltbook-worker.service -f
```

### 2.5 Stop / restart

```bash
sudo systemctl stop moltbook-api.service moltbook-worker.service
sudo systemctl restart moltbook-api.service moltbook-worker.service
```

---

## 3. macOS: launchd

Use user agents (`~/Library/LaunchAgents`) for local user-level services.
Template files in repo:
- `deploy/launchd/com.moltbook.api.plist.example`
- `deploy/launchd/com.moltbook.worker.plist.example`

### 3.1 API plist

Create `~/Library/LaunchAgents/com.moltbook.api.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.moltbook.api</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd <PROJECT_DIR> && uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000</string>
  </array>

  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string><LOG_DIR>/moltbook-api.out.log</string>
  <key>StandardErrorPath</key>
  <string><LOG_DIR>/moltbook-api.err.log</string>
</dict>
</plist>
```

### 3.2 Worker plist

Create `~/Library/LaunchAgents/com.moltbook.worker.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.moltbook.worker</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd <PROJECT_DIR> && uv run python -m src.workers.scheduler</string>
  </array>

  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string><LOG_DIR>/moltbook-worker.out.log</string>
  <key>StandardErrorPath</key>
  <string><LOG_DIR>/moltbook-worker.err.log</string>
</dict>
</plist>
```

### 3.3 Load and start

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.moltbook.api.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.moltbook.worker.plist
```

If already loaded:

```bash
launchctl kickstart -k gui/$(id -u)/com.moltbook.api
launchctl kickstart -k gui/$(id -u)/com.moltbook.worker
```

### 3.4 Check status and logs

```bash
launchctl print gui/$(id -u)/com.moltbook.api
launchctl print gui/$(id -u)/com.moltbook.worker
tail -f <LOG_DIR>/moltbook-api.out.log <LOG_DIR>/moltbook-api.err.log
tail -f <LOG_DIR>/moltbook-worker.out.log <LOG_DIR>/moltbook-worker.err.log
```

### 3.5 Stop / unload

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.moltbook.api.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.moltbook.worker.plist
```

---

## 4. Recommended Operational Practices

- `systemd` templates in repo:
  - `deploy/systemd/moltbook-api.service.example`
  - `deploy/systemd/moltbook-worker.service.example`
- Quick apply flow:
  - Copy template to target location.
  - Replace `<PROJECT_DIR>`, `<SERVICE_USER>`, `<LOG_DIR>`.
  - Start services with `systemctl` or `launchctl`.
- Keep `.env` complete and consistent before enabling services.
- Validate DB/queue readiness with `/health` after startup.
- Rotate tokens and never commit `.env`.
- Use `tmux` only for ad-hoc debugging, not as the main supervisor.
