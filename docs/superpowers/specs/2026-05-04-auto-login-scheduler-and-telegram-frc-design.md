# Auto-Login Scheduler + Telegram `/frc` — Design

**Date:** 2026-05-04
**Status:** Draft (awaiting user sign-off before implementation plan)

## Problem

The Fyers auto-login module (`auth/auth.py`) is fully implemented but never invoked automatically. A token is only minted when a gRPC client calls `GetToken` (lazy / on-demand). We want:

1. A daily login at **09:13 IST on weekdays (Mon–Fri)**, before the NSE market opens at 09:15 IST. Saturdays and Sundays are skipped.
2. A Telegram `/frc` command that **forces a fresh full TOTP login on demand**, bypassing all caches.
3. **Telegram notifications** on scheduled login success/failure and on `/frc` start/result.
4. The bot **token in `.env`** so it can rotate per environment. Chat ID also lives in `.env` (per user clarification).

## Non-Goals

- Handling NSE trading holidays beyond weekends (Diwali, Republic Day, etc.) — out of scope; a wasted login on a closed weekday is harmless. May be added later as a separate concern.
- Multiple chat recipients, multi-bot, or admin/role checks. One bot, one chat.
- Replacing or modifying the existing `get_fyers_token()` lazy fallback used by gRPC `AuthServicer`.
- Persisting Telegram update IDs / dedup. Telegram retries on non-2xx; we always return 200, so duplicates are not expected.

## Architecture

The gRPC server is a long-running process. The scheduler and Telegram webhook live as **daemon threads inside the same process** (`run_grpc.py`). Single command starts everything; daemons die with the process.

```
run_grpc.py  (single process, runs forever)
│
├─ Main thread
│   └─ gRPC server on :50051         (existing, unchanged)
│
├─ Daemon thread #1 — Scheduler
│   ├─ Startup catch-up (run once)
│   └─ Loop: sleep until next 09:13 IST weekday → login → notify → repeat
│
├─ Daemon thread #2 — Telegram webhook HTTP server
│   ├─ Binds to TELEGRAM_WEBHOOK_HOST:TELEGRAM_WEBHOOK_PORT
│   └─ POSTs validated → /frc handler → force login → reply
│
└─ One-shot bootstrap (runs in main thread before serve())
    ├─ setWebhook(TELEGRAM_WEBHOOK_URL, secret_token=...)
    └─ setMyCommands([{frc, "Force Fyers re-login"}])
```

## Time & Timezone

**All datetime operations use IST (`ZoneInfo("Asia/Kolkata")`)** — same convention as `auth/auth.py`. Concretely:

- Scheduler computes `now = datetime.now(IST)` and compares against `09:13 IST`.
- `is_trading_day(d)` operates on an IST `date` (a server in UTC would otherwise produce wrong weekdays around midnight IST).
- Telegram message timestamps render as `YYYY-MM-DD HH:MM:SS IST`.
- Token cache file `auth/.fyers_token` already stores IST timestamps; we keep that.

Trigger time defaults to `09:13` (configurable via `SCHEDULER_TRIGGER_TIME` env, format `HH:MM`).

## Components

### New: `scheduler/scheduler.py`
Pure-ish scheduling loop.

- `is_trading_day(d: date) -> bool` — `True` for Mon–Fri.
- `next_trigger_at(now: datetime, trigger_time: time) -> datetime` — returns the next IST datetime at `trigger_time` (parsed once from `SCHEDULER_TRIGGER_TIME`, default `09:13`) that falls on a weekday strictly after `now`. Pure function; easy to unit-test with a fixed clock.
- `should_run_catchup(now: datetime, trigger_time: time, cached_token_date: date | None) -> bool` — `True` iff `is_trading_day(now.date())` AND `now.time() >= trigger_time` AND (cache is empty OR `cached_token_date < now.date()`).
- `run_scheduler_loop()` — entry point called from `run_grpc.py` in a thread:
  1. If `should_run_catchup(...)`: run scheduled login now.
  2. Loop forever: sleep until `next_trigger_at(now)`, then run scheduled login.
- `_run_scheduled_login()` — calls `auth.force_login.force_full_login()`, on success/failure sends a Telegram notification.

### New: `scheduler/__init__.py`
Re-exports `run_scheduler_loop`, `is_trading_day`, `next_trigger_at`.

### New: `notify/telegram.py`
Telegram client + webhook server.

- `send_message(text: str, chat_id: int | None = None) -> bool` — POST to `https://api.telegram.org/bot<TOKEN>/sendMessage` via stdlib `urllib.request`, body `{"chat_id": chat_id or TELEGRAM_CHAT_ID, "text": text}`. Returns `True` on HTTP 2xx; logs and returns `False` otherwise. Retries up to 3× on transient `URLError`. The `chat_id` parameter is used by `/frc` replies to route back to the originating chat; scheduler notifications omit it and fall through to env's `TELEGRAM_CHAT_ID`.
- `register_bot()` — one-shot at startup:
  1. POST `setWebhook` with `{"url": TELEGRAM_WEBHOOK_URL, "secret_token": TELEGRAM_WEBHOOK_SECRET}`.
  2. POST `setMyCommands` with `[{"command": "frc", "description": "Force Fyers re-login"}]`.
  Failure is logged at `WARNING` and is non-fatal.
- `run_webhook_server(host, port)` — stdlib `http.server.ThreadingHTTPServer` with a single `BaseHTTPRequestHandler` subclass. Threading so a slow `/frc` doesn't block subsequent updates.
- `_TelegramHandler.do_POST()`:
  1. Validate `X-Telegram-Bot-Api-Secret-Token` header against `TELEGRAM_WEBHOOK_SECRET` → 401 if mismatch (early return).
  2. Parse JSON body → `Update` dict; on parse error, 400 + log (early return).
  3. Validate `update["message"]["chat"]["id"] == int(TELEGRAM_CHAT_ID)` — if mismatch, log warning, send 200 + empty body, return without dispatching. (Defense-in-depth beyond the secret header.)
  4. **Send 200 OK + empty body now** (`send_response(200); send_header("Content-Length","0"); end_headers(); wfile.flush()`). The response is on the wire before any slow work begins, so Telegram never times out and never retries.
  5. Read `update["message"]["text"]`; if `== "/frc"` → call `_handle_frc(update)` synchronously in this same handler thread (`ThreadingHTTPServer` gives every request its own thread, so this doesn't block other requests). Unknown commands: do nothing.
- `_handle_frc(update)`:
  1. `chat_id = update["message"]["chat"]["id"]` (validated == `TELEGRAM_CHAT_ID` above; we use the value from the update for symmetry with future multi-chat changes).
  2. `send_message("🔄 Forcing Fyers re-login at <time IST>...", chat_id=chat_id)`.
  3. Call `auth.force_login.force_full_login()`.
  4. On success: `send_message("✅ Re-login complete at <time IST> — token valid 24h", chat_id=chat_id)`.
  5. On failure: `send_message("❌ Re-login failed: <step + reason>", chat_id=chat_id)`.
  6. Wrapped in try/except — exceptions log full traceback and `send_message("❌ Internal error — check server logs", chat_id=chat_id)`. Never raises (the 200 was already sent in step 4 of `do_POST`; a raise here would only show in logs).

Note: `send_message(text, chat_id=None)` — when `chat_id` is omitted, defaults to `TELEGRAM_CHAT_ID` (used by scheduler notifications). When provided, sends to that specific chat (used by `/frc` replies).

### New: `notify/__init__.py`
Re-exports `send_message`, `register_bot`, `run_webhook_server`.

### New: `auth/force_login.py`
Thin helper that names the "force" intent at the call site.

- `force_full_login() -> dict` — bypasses cache and refresh-token; runs steps 1–5 from scratch via existing `auth.full_totp_login()`; on success calls `auth.save_token(tokens)` and returns the tokens dict; on failure returns `{}`.
- A module-level `threading.Lock` serializes concurrent calls (scheduler 09:13 + user `/frc` 09:13:02 will not race).

### Edited: `config/settings.py`
Add the following env-backed constants (with sensible defaults where it makes sense):

```python
TELEGRAM_BOT_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_WEBHOOK_URL    = os.getenv("TELEGRAM_WEBHOOK_URL")
TELEGRAM_WEBHOOK_HOST   = os.getenv("TELEGRAM_WEBHOOK_HOST", "0.0.0.0")
TELEGRAM_WEBHOOK_PORT   = int(os.getenv("TELEGRAM_WEBHOOK_PORT", "8080"))
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")
SCHEDULER_TRIGGER_TIME  = os.getenv("SCHEDULER_TRIGGER_TIME", "09:13")  # HH:MM IST
```

The trigger-time string is parsed once at scheduler-thread startup; bad format → log error and fall back to default `"09:13"`.

### Edited: `.env` (developer-facing)
The user adds (values redacted in this doc):

```
TELEGRAM_BOT_TOKEN=<bot token from BotFather>
TELEGRAM_CHAT_ID=<numeric chat id>
TELEGRAM_WEBHOOK_URL=https://<your-public-host>/telegram
TELEGRAM_WEBHOOK_HOST=0.0.0.0
TELEGRAM_WEBHOOK_PORT=8080
TELEGRAM_WEBHOOK_SECRET=<generate a random 32+ char string>
```

`SCHEDULER_TRIGGER_TIME` is optional; omit to keep the 09:13 default.

### Edited: `run_grpc.py`
Before calling `serve()`:
1. `notify.register_bot()` — best-effort, non-fatal.
2. `threading.Thread(target=notify.run_webhook_server, args=(host, port), daemon=True).start()`.
3. `threading.Thread(target=scheduler.run_scheduler_loop, daemon=True).start()`.

Then `serve(...)` blocks the main thread as today.

## Data Flow

### 1) Scheduled login (Mon–Fri 09:13 IST)
```
scheduler thread wakes at 09:13:00 IST
  → is_trading_day(today)? if no → recompute next, sleep
  → auth.force_login.force_full_login()
       → step1 → step2 → step3 → step4 → step5 → save_token()
  → on success: notify.telegram.send_message("✅ Fyers login successful at HH:MM:SS IST")
  → on failure: notify.telegram.send_message("❌ Fyers scheduled login FAILED at HH:MM:SS IST — <step + reason>")
  → sleep until next_trigger_at(now)
```

### 2) `/frc` from Telegram
```
User types /frc in Telegram
  → Telegram POSTs Update JSON to TELEGRAM_WEBHOOK_URL
       headers: X-Telegram-Bot-Api-Secret-Token: <secret>
  → handler validates secret header (401 on mismatch)
  → handler parses body (400 on parse error)
  → handler validates update.message.chat.id == TELEGRAM_CHAT_ID
       (mismatch → 200 OK + no body, no login, just log warning)
  → handler sends 200 OK + empty body NOW (response on the wire before any work)
  → handler then, in same thread:
       send_message("🔄 Forcing Fyers re-login at HH:MM:SS IST...", chat_id=chat_id)
       auth.force_login.force_full_login()
       on success: send_message("✅ Re-login complete at HH:MM:SS IST — token valid 24h", chat_id=chat_id)
       on failure: send_message("❌ Re-login failed: <step + reason>", chat_id=chat_id)
```

### 3) Startup catch-up
```
On run_grpc.py boot, scheduler thread first:
  trigger_time = parse(SCHEDULER_TRIGGER_TIME)   # e.g. 09:13 IST
  now = datetime.now(IST)
  cached = auth.load_token()
  cached_date = parse(cached["timestamp"]).date() if cached else None
  if should_run_catchup(now, trigger_time, cached_date):
       run scheduled login now
  → enter the normal loop, sleeping until next_trigger_at(now, trigger_time)
```

### 4) Telegram bootstrap (one-shot at startup, before threads start)
```
POST https://api.telegram.org/bot<TOKEN>/setWebhook
     body: {"url": TELEGRAM_WEBHOOK_URL, "secret_token": TELEGRAM_WEBHOOK_SECRET}
POST https://api.telegram.org/bot<TOKEN>/setMyCommands
     body: {"commands": [{"command": "frc", "description": "Force Fyers re-login"}]}
log success / non-fatal warning on failure
```

### Notification policy
- ✅ Notify on scheduled login success.
- ❌ Notify on scheduled login failure (loud — you want to know).
- 🔄/✅/❌ Reply to chat on `/frc` start and result (user is actively waiting).
- 🚫 Do **not** notify on startup-catchup if the cached token is still fresh (no work happened, no message).

## Error Handling

| Failure | Behaviour |
|---|---|
| Scheduled login fails (any of steps 1–5, network, etc.) | Token NOT saved (atomic — old token survives until it actually expires). Telegram alert. Scheduler does NOT retry; sleeps until next 09:13. `/frc` is the manual escape hatch. Existing `get_fyers_token()` lazy fallback still works. |
| `/frc` login fails | Reply with failure reason. No retry. User can `/frc` again. |
| Telegram unreachable (sendMessage fails) | Log error. Do NOT raise. Login itself is unaffected. Notification is best-effort. |
| Wrong webhook secret header | 401. No body. Log warning. |
| Wrong webhook path | 404. |
| Malformed webhook JSON | 400. Log. |
| Update from non-configured chat | 200 OK. No reply. No login. Log warning with the offending `chat_id`. |
| Unknown command in valid update | 200 OK. No reply. (Don't make the bot a noise generator.) |
| Webhook handler exception | Caught at handler boundary. Reply `❌ Internal error — check server logs`. Full traceback logged. Always 200 to Telegram. |
| Bootstrap (setWebhook / setMyCommands) fails on startup | Log WARNING, continue. gRPC + scheduler still come up. Re-bootstrap by restarting once URL is live. |
| Concurrent logins (scheduler + `/frc` overlap) | `threading.Lock` in `auth/force_login.py` serializes. Both calls eventually run; second sees fresh token. No duplicate notifications because each caller owns its own message logic. |

## Testing

### Unit tests (pytest, no network)
- `scheduler/test_scheduler.py`:
  - `next_trigger_at(now, trigger_time=time(9,13))` fixed-clock cases:
    - Mon 08:00 → Mon 09:13
    - Mon 09:14 → Tue 09:13
    - Fri 09:14 → Mon 09:13
    - Sat 10:00 → Mon 09:13
    - Sun 23:59 → Mon 09:13
    - Custom trigger_time=10:00 → next Mon–Fri 10:00
  - `is_trading_day(d)`: Mon–Fri True, Sat/Sun False.
  - `should_run_catchup(now, trigger_time, cached_date)`:
    - Weekday 10:00, no cache → True
    - Weekday 10:00, cache = today → False
    - Weekday 10:00, cache = yesterday → True
    - Weekday 08:00, any cache → False
    - Sat 10:00, any cache → False
- `notify/test_telegram.py`:
  - Webhook returns 401 on missing/mismatched `X-Telegram-Bot-Api-Secret-Token`.
  - Returns 200 + no body for `chat_id` not matching `TELEGRAM_CHAT_ID` (no login fired).
  - Returns 200 + no body for unknown commands.
  - Returns 200 + log on malformed JSON.
  - `send_message(text)` POSTs with `chat_id=TELEGRAM_CHAT_ID`; `send_message(text, chat_id=42)` POSTs with `chat_id=42`.
  - `send_message` retries on transient `URLError`, gives up after 3 attempts, returns False.

### Mocked integration tests
- `test_force_login_serializes` — concurrent `force_full_login()` calls run TOTP flow only one-at-a-time (stub network calls in `auth.auth`, assert call count under `ThreadPoolExecutor`).
- `test_startup_catchup_runs_once` — given a stale cached token + Mon 10:00 IST mocked clock, the scheduler thread runs login once on boot and not again until 09:13 next weekday.

### Manual smoke checklist
1. `python run_grpc.py` → logs show `gRPC server listening`, `scheduler started`, `telegram bootstrap ok`.
2. `curl -X POST $TELEGRAM_WEBHOOK_URL` (no secret header) → 401.
3. Send `/frc` from Telegram → receive `🔄 Forcing...` then `✅ Re-login complete` within ~10 s.
4. Set system clock to weekday 09:12 IST, restart, wait 1 min → scheduler fires; receive ✅ in Telegram.
5. Set system clock to Saturday 09:13 IST, restart → no login, no Telegram.
6. Stop the public tunnel, send `/frc` → no reply (Telegram can't reach us); restart tunnel → next `/frc` works.

### Out of scope for tests
- The actual Fyers TOTP flow (already exists in `auth/auth.py`).
- The Telegram API itself.
- Real public webhook reachability (depends on infra you control).

## Deployment Notes

- The webhook URL must be **HTTPS** (Telegram requirement).
- The local bind port must be reachable from the public URL (reverse proxy / port forward / tunnel — your infra).
- The webhook secret should be ≥32 random chars; rotate if leaked. Telegram sends it as a header on every POST so we can validate the source.
- Bot token rotation: change `TELEGRAM_BOT_TOKEN` in `.env`, restart `run_grpc.py`. Bootstrap will re-register.

## Open Items (none blocking — defaults chosen)

- **Trigger time:** defaults to `09:13`. Configurable via `SCHEDULER_TRIGGER_TIME`. Adjust if NSE pre-open changes.
- **NSE holidays beyond weekends:** explicitly out of scope. If a wasted Diwali login becomes a real annoyance, add a `config/nse_holidays_<year>.py` and check it in `is_trading_day`.
