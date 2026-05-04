# Auto-Login Scheduler + Telegram `/frc` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing Fyers auto-login module into a long-running daily scheduler (Mon–Fri 09:13 IST) and add a Telegram `/frc` webhook command that forces a fresh full TOTP login on demand, with success/failure notifications via Telegram.

**Architecture:** Two daemon threads inside `run_grpc.py` — a scheduler loop and a stdlib HTTP webhook server — share `auth/auth.py` via a thin `auth/force_login.py` helper that holds a `threading.Lock`. Scheduler computes `next_trigger_at(now, trigger_time)` using `zoneinfo.ZoneInfo("Asia/Kolkata")` and sleeps until the next weekday trigger. Webhook validates a Telegram secret header + configured chat_id, returns 200 immediately, then runs login synchronously in the per-request thread (provided by `ThreadingHTTPServer`).

**Tech Stack:** Python 3.12 stdlib only — `threading`, `http.server`, `urllib.request`, `zoneinfo`, `json`, `logging`. No new third-party deps. Tests use `pytest` + `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-05-04-auto-login-scheduler-and-telegram-frc-design.md`

---

## File Structure

| File | Purpose |
|---|---|
| `scheduler/__init__.py` (new) | Re-export public API: `run_scheduler_loop`, `is_trading_day`, `next_trigger_at`. |
| `scheduler/scheduler.py` (new) | Pure functions (`is_trading_day`, `next_trigger_at`, `should_run_catchup`) + loop (`run_scheduler_loop`, `_run_scheduled_login`). |
| `scheduler/test_scheduler.py` (new) | Unit tests for the pure functions and the loop entry point. |
| `notify/__init__.py` (new) | Re-export public API: `send_message`, `register_bot`, `run_webhook_server`. |
| `notify/telegram.py` (new) | Telegram client (`send_message`), bootstrap (`register_bot`), webhook server (`run_webhook_server`, `_TelegramHandler`, `_handle_frc`). |
| `notify/test_telegram.py` (new) | Unit tests for client + handler + bootstrap. |
| `auth/force_login.py` (new) | `force_full_login()` — thin lock-protected wrapper over `auth.full_totp_login()` + `auth.save_token()`. |
| `auth/test_force_login.py` (new) | Unit tests for the lock + bypass-cache behavior. |
| `config/settings.py` (modified) | Add 7 env-backed Telegram + scheduler vars. |
| `run_grpc.py` (modified) | Bootstrap + start daemon threads before `serve()`. |
| `pyproject.toml` (modified) | Add `pytest` and `pytest-mock` to optional `dev` dependencies; add `[tool.pytest.ini_options]`. |
| `.env` (modified by user, not by code) | New Telegram + scheduler env vars (documented in Task 13). |

---

## Task 1: Project setup — pytest + package skeletons

**Files:**
- Modify: `pyproject.toml`
- Create: `scheduler/__init__.py`
- Create: `scheduler/scheduler.py` (empty)
- Create: `scheduler/test_scheduler.py` (empty)
- Create: `notify/__init__.py`
- Create: `notify/telegram.py` (empty)
- Create: `notify/test_telegram.py` (empty)
- Create: `auth/force_login.py` (empty)
- Create: `auth/test_force_login.py` (empty)

- [ ] **Step 1: Add pytest dev dependency + pytest config to `pyproject.toml`**

Replace `pyproject.toml` with:

```toml
[project]
name = "analyzer"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fyers-apiv3>=3.1.12",
    "grpcio>=1.60.0",
    "grpcio-reflection>=1.60.0",
    "grpcio-tools>=1.60.0",
    "mcp>=1.0.0",
    "pyotp>=2.9.0",
    "python-dotenv>=1.2.2",
    "requests>=2.31.0",
    "tzdata>=2024.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-mock>=3.12.0",
]

[tool.pytest.ini_options]
testpaths = ["scheduler", "notify", "auth"]
python_files = "test_*.py"
```

- [ ] **Step 2: Install dev dependencies**

Run:

```bash
uv sync --extra dev
```

Expected: `uv` resolves and installs pytest + pytest-mock.

- [ ] **Step 3: Create empty package skeletons**

Create the empty files (the actual content is filled in by later tasks):

`scheduler/__init__.py`:
```python
```

`scheduler/scheduler.py`:
```python
```

`scheduler/test_scheduler.py`:
```python
```

`notify/__init__.py`:
```python
```

`notify/telegram.py`:
```python
```

`notify/test_telegram.py`:
```python
```

`auth/force_login.py`:
```python
```

`auth/test_force_login.py`:
```python
```

- [ ] **Step 4: Verify pytest discovers the empty test files**

Run:

```bash
uv run pytest --collect-only
```

Expected: `0 tests collected` and no errors. Confirms pytest can import the empty packages.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock scheduler/ notify/ auth/force_login.py auth/test_force_login.py
git commit -m "chore: scaffold scheduler/, notify/, force_login, pytest dev dep"
```

---

## Task 2: `config/settings.py` — Telegram + scheduler env vars

**Files:**
- Modify: `config/settings.py`

- [ ] **Step 1: Add the 7 new env-backed constants**

Read `config/settings.py` and find the section ending with `GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))`. Append after it:

```python

# ============================================================
# TELEGRAM BOT (auto-login notifications + /frc command)
# ============================================================
TELEGRAM_BOT_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_WEBHOOK_URL    = os.getenv("TELEGRAM_WEBHOOK_URL")
TELEGRAM_WEBHOOK_HOST   = os.getenv("TELEGRAM_WEBHOOK_HOST", "0.0.0.0")
TELEGRAM_WEBHOOK_PORT   = int(os.getenv("TELEGRAM_WEBHOOK_PORT", "8080"))
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")

# ============================================================
# SCHEDULER
# ============================================================
SCHEDULER_TRIGGER_TIME  = os.getenv("SCHEDULER_TRIGGER_TIME", "09:13")  # HH:MM IST
```

- [ ] **Step 2: Verify imports still work**

Run:

```bash
uv run python -c "import config.settings as s; print(s.SCHEDULER_TRIGGER_TIME, s.TELEGRAM_WEBHOOK_PORT)"
```

Expected output: `09:13 8080`

- [ ] **Step 3: Commit**

```bash
git add config/settings.py
git commit -m "feat: add Telegram + scheduler env vars to settings"
```

---

## Task 3: `scheduler/scheduler.py` — `is_trading_day`

**Files:**
- Create: `scheduler/scheduler.py`
- Create: `scheduler/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

Replace `scheduler/test_scheduler.py` with:

```python
"""Unit tests for scheduler.scheduler."""
from datetime import date

import pytest

from scheduler.scheduler import is_trading_day


class TestIsTradingDay:
    @pytest.mark.parametrize("d, expected", [
        (date(2026, 5, 4), True),   # Monday
        (date(2026, 5, 5), True),   # Tuesday
        (date(2026, 5, 6), True),   # Wednesday
        (date(2026, 5, 7), True),   # Thursday
        (date(2026, 5, 8), True),   # Friday
        (date(2026, 5, 9), False),  # Saturday
        (date(2026, 5, 10), False), # Sunday
    ])
    def test_weekdays_are_trading_days_weekends_are_not(self, d, expected):
        assert is_trading_day(d) is expected
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest scheduler/test_scheduler.py -v
```

Expected: `ImportError: cannot import name 'is_trading_day' from 'scheduler.scheduler'`.

- [ ] **Step 3: Write minimal implementation**

Replace `scheduler/scheduler.py` with:

```python
"""Daily 09:13 IST weekday auto-login scheduler.

Runs as a daemon thread inside run_grpc.py. Computes the next IST trigger
(default 09:13, configurable via SCHEDULER_TRIGGER_TIME), sleeps until then,
fires force_full_login(), and repeats. Skips weekends.
"""
from datetime import date


def is_trading_day(d: date) -> bool:
    """True for Mon–Fri (NSE weekday). Sat/Sun are non-trading days."""
    return d.weekday() < 5  # Mon=0 ... Sun=6
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest scheduler/test_scheduler.py -v
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add scheduler/scheduler.py scheduler/test_scheduler.py
git commit -m "feat(scheduler): add is_trading_day"
```

---

## Task 4: `scheduler/scheduler.py` — `next_trigger_at`

**Files:**
- Modify: `scheduler/scheduler.py`
- Modify: `scheduler/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

Append to `scheduler/test_scheduler.py`:

```python
from datetime import datetime, time
from zoneinfo import ZoneInfo

from scheduler.scheduler import next_trigger_at

IST = ZoneInfo("Asia/Kolkata")


def _ist(year, month, day, hh, mm):
    return datetime(year, month, day, hh, mm, tzinfo=IST)


class TestNextTriggerAt:
    TRIGGER = time(9, 13)

    def test_monday_morning_returns_same_day_0913(self):
        # Mon 2026-05-04 08:00 IST → Mon 2026-05-04 09:13 IST
        now = _ist(2026, 5, 4, 8, 0)
        result = next_trigger_at(now, self.TRIGGER)
        assert result == _ist(2026, 5, 4, 9, 13)

    def test_monday_after_trigger_returns_tuesday(self):
        # Mon 2026-05-04 09:14 IST → Tue 2026-05-05 09:13 IST
        now = _ist(2026, 5, 4, 9, 14)
        result = next_trigger_at(now, self.TRIGGER)
        assert result == _ist(2026, 5, 5, 9, 13)

    def test_friday_after_trigger_skips_weekend_to_monday(self):
        # Fri 2026-05-08 09:14 IST → Mon 2026-05-11 09:13 IST
        now = _ist(2026, 5, 8, 9, 14)
        result = next_trigger_at(now, self.TRIGGER)
        assert result == _ist(2026, 5, 11, 9, 13)

    def test_saturday_morning_returns_monday(self):
        # Sat 2026-05-09 10:00 IST → Mon 2026-05-11 09:13 IST
        now = _ist(2026, 5, 9, 10, 0)
        result = next_trigger_at(now, self.TRIGGER)
        assert result == _ist(2026, 5, 11, 9, 13)

    def test_sunday_late_returns_monday(self):
        # Sun 2026-05-10 23:59 IST → Mon 2026-05-11 09:13 IST
        now = _ist(2026, 5, 10, 23, 59)
        result = next_trigger_at(now, self.TRIGGER)
        assert result == _ist(2026, 5, 11, 9, 13)

    def test_custom_trigger_time(self):
        # Mon 2026-05-04 08:00 IST with trigger=10:00 → Mon 10:00
        now = _ist(2026, 5, 4, 8, 0)
        result = next_trigger_at(now, time(10, 0))
        assert result == _ist(2026, 5, 4, 10, 0)

    def test_exactly_at_trigger_returns_strictly_after(self):
        # If now == trigger to the second, the *next* trigger is tomorrow's.
        # We want strictly after, so 09:13:00 → tomorrow's 09:13.
        now = _ist(2026, 5, 4, 9, 13)
        result = next_trigger_at(now, self.TRIGGER)
        assert result == _ist(2026, 5, 5, 9, 13)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest scheduler/test_scheduler.py::TestNextTriggerAt -v
```

Expected: `ImportError: cannot import name 'next_trigger_at'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scheduler/scheduler.py`:

```python
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def next_trigger_at(now: datetime, trigger_time: time) -> datetime:
    """Return the next IST datetime at trigger_time on a Mon–Fri, strictly after `now`.

    `now` must be timezone-aware; we convert to IST internally so callers can
    pass either an IST or UTC datetime safely.
    """
    now_ist = now.astimezone(IST)
    candidate = datetime.combine(now_ist.date(), trigger_time, tzinfo=IST)
    # If today's trigger has already passed (or is exactly equal), move to tomorrow
    if candidate <= now_ist:
        candidate += timedelta(days=1)
    # Skip Sat/Sun
    while not is_trading_day(candidate.date()):
        candidate += timedelta(days=1)
    return candidate
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest scheduler/test_scheduler.py -v
```

Expected: All `TestNextTriggerAt` cases pass + the existing `TestIsTradingDay` cases still pass.

- [ ] **Step 5: Commit**

```bash
git add scheduler/scheduler.py scheduler/test_scheduler.py
git commit -m "feat(scheduler): add next_trigger_at with weekday + IST handling"
```

---

## Task 5: `scheduler/scheduler.py` — `should_run_catchup`

**Files:**
- Modify: `scheduler/scheduler.py`
- Modify: `scheduler/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

Append to `scheduler/test_scheduler.py`:

```python
from scheduler.scheduler import should_run_catchup


class TestShouldRunCatchup:
    TRIGGER = time(9, 13)

    def test_weekday_after_trigger_no_cache_runs(self):
        # Mon 10:00, no cached token → run catchup
        now = _ist(2026, 5, 4, 10, 0)
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=None) is True

    def test_weekday_after_trigger_cache_today_skips(self):
        # Mon 10:00, cache from same day → skip
        now = _ist(2026, 5, 4, 10, 0)
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=date(2026, 5, 4)) is False

    def test_weekday_after_trigger_cache_yesterday_runs(self):
        # Mon 10:00, cache from yesterday → run catchup
        now = _ist(2026, 5, 4, 10, 0)
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=date(2026, 5, 3)) is True

    def test_weekday_before_trigger_skips(self):
        # Mon 08:00, any cache state → skip (the regular trigger will fire later)
        now = _ist(2026, 5, 4, 8, 0)
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=None) is False
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=date(2026, 5, 3)) is False

    def test_saturday_skips(self):
        # Sat 10:00, regardless of cache → skip
        now = _ist(2026, 5, 9, 10, 0)
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=None) is False
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=date(2026, 5, 8)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest scheduler/test_scheduler.py::TestShouldRunCatchup -v
```

Expected: `ImportError: cannot import name 'should_run_catchup'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scheduler/scheduler.py`:

```python
def should_run_catchup(
    now: datetime,
    trigger_time: time,
    cached_token_date: date | None,
) -> bool:
    """True iff we should run a catchup login on startup.

    Conditions: today is a trading day AND we are at-or-past today's trigger AND
    we don't already have a fresh cached token from today.
    """
    now_ist = now.astimezone(IST)
    if not is_trading_day(now_ist.date()):
        return False
    if now_ist.time() < trigger_time:
        return False
    if cached_token_date is not None and cached_token_date >= now_ist.date():
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest scheduler/test_scheduler.py -v
```

Expected: All scheduler tests pass.

- [ ] **Step 5: Commit**

```bash
git add scheduler/scheduler.py scheduler/test_scheduler.py
git commit -m "feat(scheduler): add should_run_catchup for boot-time check"
```

---

## Task 6: `auth/force_login.py` — bypass cache + lock-serialized

**Files:**
- Create: `auth/force_login.py`
- Create: `auth/test_force_login.py`

- [ ] **Step 1: Write the failing test**

Replace `auth/test_force_login.py` with:

```python
"""Unit tests for auth.force_login.

force_full_login() must:
- Bypass cache: never call load_token().
- Skip refresh path: never call refresh_access_token().
- Run full TOTP via auth.full_totp_login() and persist via auth.save_token().
- Serialize concurrent calls via a module-level threading.Lock.
"""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock

import pytest

from auth import force_login


class TestForceFullLogin:
    def test_returns_tokens_on_success_and_saves(self):
        fake_tokens = {"access_token": "a", "refresh_token": "r"}
        with patch("auth.force_login.full_totp_login", return_value=fake_tokens) as m_login, \
             patch("auth.force_login.save_token") as m_save:
            result = force_login.force_full_login()
        assert result == fake_tokens
        m_login.assert_called_once_with()
        m_save.assert_called_once_with(fake_tokens)

    def test_returns_empty_on_failure_and_does_not_save(self):
        with patch("auth.force_login.full_totp_login", return_value={}) as m_login, \
             patch("auth.force_login.save_token") as m_save:
            result = force_login.force_full_login()
        assert result == {}
        m_login.assert_called_once_with()
        m_save.assert_not_called()

    def test_does_not_call_load_token_or_refresh(self):
        # Force login MUST NOT consult cache or refresh; both shortcuts skipped.
        with patch("auth.force_login.full_totp_login", return_value={"access_token": "x", "refresh_token": "y"}), \
             patch("auth.force_login.save_token"), \
             patch("auth.auth.load_token") as m_load, \
             patch("auth.auth.refresh_access_token") as m_refresh:
            force_login.force_full_login()
        m_load.assert_not_called()
        m_refresh.assert_not_called()

    def test_concurrent_calls_serialize(self):
        # Two threads call force_full_login() at the same time.
        # full_totp_login is mocked to record the maximum number of overlapping
        # invocations. Lock guarantees max == 1.
        in_flight = 0
        max_in_flight = 0
        lock = __import__("threading").Lock()

        def slow_login():
            nonlocal in_flight, max_in_flight
            with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            # simulate work
            __import__("time").sleep(0.05)
            with lock:
                in_flight -= 1
            return {"access_token": "a", "refresh_token": "r"}

        with patch("auth.force_login.full_totp_login", side_effect=slow_login), \
             patch("auth.force_login.save_token"):
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(force_login.force_full_login) for _ in range(4)]
                for f in futures:
                    f.result()
        assert max_in_flight == 1, f"expected serialized calls, got {max_in_flight} concurrent"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest auth/test_force_login.py -v
```

Expected: `AttributeError: module 'auth.force_login' has no attribute 'force_full_login'` (or `ImportError`).

- [ ] **Step 3: Write minimal implementation**

Replace `auth/force_login.py` with:

```python
"""Force a fresh full TOTP login, bypassing all caches and refresh shortcuts.

Used by:
  - the daily 09:13 IST scheduler
  - the Telegram /frc command

Concurrent callers are serialized by a module-level threading.Lock so the
TOTP flow never runs twice in parallel (which would double-charge the
underlying API and could trigger anti-fraud throttling on Fyers' side).
"""
import logging
import threading

from auth.auth import full_totp_login, save_token

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()


def force_full_login() -> dict:
    """Run the full 5-step TOTP flow and persist the result.

    Bypasses load_token() and refresh_access_token() — every call hits steps 1-5.
    On success, save_token() persists the new access + refresh tokens.

    Returns the tokens dict on success, {} on failure.
    """
    with _LOCK:
        logger.info("force_full_login: starting full TOTP flow")
        tokens = full_totp_login()
        if tokens.get("access_token"):
            save_token(tokens)
            logger.info("force_full_login: success")
            return tokens
        logger.error("force_full_login: failed (full_totp_login returned empty)")
        return {}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest auth/test_force_login.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add auth/force_login.py auth/test_force_login.py
git commit -m "feat(auth): add force_full_login with threading.Lock"
```

---

## Task 7: `notify/telegram.py` — `send_message` with retries

**Files:**
- Create: `notify/telegram.py`
- Create: `notify/test_telegram.py`

- [ ] **Step 1: Write the failing test**

Replace `notify/test_telegram.py` with:

```python
"""Unit tests for notify.telegram."""
import json
from unittest.mock import patch, MagicMock
from urllib.error import URLError

import pytest


class TestSendMessage:
    def test_uses_default_chat_id_from_settings(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT123")
        monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", "111")

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: None
            return resp

        with patch("notify.telegram.urlopen", side_effect=fake_urlopen):
            ok = t.send_message("hello")

        assert ok is True
        assert captured["url"] == "https://api.telegram.org/botBOT123/sendMessage"
        assert captured["body"] == {"chat_id": "111", "text": "hello"}

    def test_explicit_chat_id_overrides_default(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT123")
        monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", "111")

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: None
            return resp

        with patch("notify.telegram.urlopen", side_effect=fake_urlopen):
            ok = t.send_message("hello", chat_id=42)

        assert ok is True
        assert captured["body"]["chat_id"] == 42

    def test_retries_on_transient_urlerror_then_succeeds(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT")
        monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", "111")
        monkeypatch.setattr(t, "_RETRY_DELAY", 0)

        attempts = {"n": 0}

        def fake_urlopen(req, timeout=None):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise URLError("transient")
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: None
            return resp

        with patch("notify.telegram.urlopen", side_effect=fake_urlopen):
            ok = t.send_message("hello")
        assert ok is True
        assert attempts["n"] == 3

    def test_returns_false_after_max_retries(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT")
        monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", "111")
        monkeypatch.setattr(t, "_RETRY_DELAY", 0)

        with patch("notify.telegram.urlopen", side_effect=URLError("down")):
            ok = t.send_message("hello")
        assert ok is False

    def test_returns_false_when_bot_token_missing(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", None)
        monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", "111")
        # No urlopen patch — function should short-circuit before any HTTP call.
        ok = t.send_message("hello")
        assert ok is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest notify/test_telegram.py::TestSendMessage -v
```

Expected: `ImportError: cannot import name 'telegram' from 'notify'` (or attribute errors).

- [ ] **Step 3: Write minimal implementation**

Replace `notify/telegram.py` with:

```python
"""Telegram bot client + webhook server for Fyers auto-login notifications.

Uses stdlib only: urllib.request for HTTP, http.server for the webhook.
Reads TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_WEBHOOK_URL,
TELEGRAM_WEBHOOK_SECRET from config.settings.
"""
import json
import logging
import time as _time
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from config.settings import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org"
_MAX_RETRIES = 3
_RETRY_DELAY = 1  # seconds; tests monkeypatch this to 0
_HTTP_TIMEOUT = 10


def send_message(text: str, chat_id: int | str | None = None) -> bool:
    """POST to Telegram sendMessage. Returns True on 2xx, False otherwise.

    chat_id: when None, falls back to TELEGRAM_CHAT_ID from env.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("send_message: TELEGRAM_BOT_TOKEN not set; skipping")
        return False
    target_chat = chat_id if chat_id is not None else TELEGRAM_CHAT_ID
    if target_chat is None:
        logger.warning("send_message: no chat_id and TELEGRAM_CHAT_ID not set; skipping")
        return False

    url = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": target_chat, "text": text}).encode()
    headers = {"Content-Type": "application/json"}

    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = Request(url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                if 200 <= resp.status < 300:
                    return True
                logger.warning(f"send_message: HTTP {resp.status}")
                return False
        except HTTPError as e:
            logger.warning(f"send_message: HTTPError {e.code}")
            return False
        except URLError as e:
            last_err = e
            logger.debug(f"send_message: URLError attempt {attempt}/{_MAX_RETRIES}: {e}")
            if attempt < _MAX_RETRIES:
                _time.sleep(_RETRY_DELAY)
    logger.error(f"send_message: gave up after {_MAX_RETRIES} attempts: {last_err}")
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest notify/test_telegram.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add notify/telegram.py notify/test_telegram.py
git commit -m "feat(notify): add Telegram send_message with retries"
```

---

## Task 8: `notify/telegram.py` — `_TelegramHandler` (webhook validation)

**Files:**
- Modify: `notify/telegram.py`
- Modify: `notify/test_telegram.py`

This task spins up an actual `ThreadingHTTPServer` on a random free port and sends real HTTP requests to it via `urllib`. That's the cleanest way to exercise `BaseHTTPRequestHandler` end-to-end.

- [ ] **Step 1: Write the failing test**

Append to `notify/test_telegram.py`:

```python
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def _start_test_server(monkeypatch, secret="SECRET", chat_id_env="111"):
    """Start the webhook server on a random free port and return (server, port).

    The caller is responsible for shutting it down.
    """
    from notify import telegram as t
    monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", chat_id_env)
    server = ThreadingHTTPServer(("127.0.0.1", 0), t._TelegramHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _post(port, body: dict, headers: dict | None = None) -> tuple[int, str]:
    """POST JSON to the test server. Returns (status, body_text). HTTPError → (code, "")."""
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = Request(f"http://127.0.0.1:{port}/", data=data, headers=h, method="POST")
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode()
    except HTTPError as e:
        return e.code, ""


class TestTelegramHandler:
    def test_missing_secret_header_returns_401(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET")
        try:
            status, _ = _post(port, {"message": {"chat": {"id": 111}, "text": "/frc"}})
            assert status == 401
        finally:
            server.shutdown()

    def test_wrong_secret_header_returns_401(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET")
        try:
            status, _ = _post(
                port,
                {"message": {"chat": {"id": 111}, "text": "/frc"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "WRONG"},
            )
            assert status == 401
        finally:
            server.shutdown()

    def test_malformed_json_returns_400(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET")
        try:
            req = Request(
                f"http://127.0.0.1:{port}/",
                data=b"{not json",
                headers={
                    "Content-Type": "application/json",
                    "X-Telegram-Bot-Api-Secret-Token": "SECRET",
                },
                method="POST",
            )
            try:
                urlopen(req, timeout=5)
                assert False, "expected HTTPError"
            except HTTPError as e:
                assert e.code == 400
        finally:
            server.shutdown()

    def test_chat_id_mismatch_returns_200_no_login(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET", chat_id_env="111")
        from notify import telegram as t
        called = {"frc": 0}
        monkeypatch.setattr(t, "_handle_frc", lambda update: called.__setitem__("frc", called["frc"] + 1))
        try:
            status, _ = _post(
                port,
                {"message": {"chat": {"id": 999}, "text": "/frc"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "SECRET"},
            )
            assert status == 200
            # Give any (incorrect) async dispatch a chance to fire — there should be none.
            __import__("time").sleep(0.05)
            assert called["frc"] == 0
        finally:
            server.shutdown()

    def test_unknown_command_returns_200_no_login(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET", chat_id_env="111")
        from notify import telegram as t
        called = {"frc": 0}
        monkeypatch.setattr(t, "_handle_frc", lambda update: called.__setitem__("frc", called["frc"] + 1))
        try:
            status, _ = _post(
                port,
                {"message": {"chat": {"id": 111}, "text": "/something_else"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "SECRET"},
            )
            assert status == 200
            __import__("time").sleep(0.05)
            assert called["frc"] == 0
        finally:
            server.shutdown()

    def test_frc_with_valid_secret_and_chat_dispatches(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET", chat_id_env="111")
        from notify import telegram as t
        called = {"frc": 0, "update": None}

        def fake_handle(update):
            called["frc"] += 1
            called["update"] = update

        monkeypatch.setattr(t, "_handle_frc", fake_handle)
        try:
            status, _ = _post(
                port,
                {"message": {"chat": {"id": 111}, "text": "/frc"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "SECRET"},
            )
            assert status == 200
            # _handle_frc runs synchronously after the 200 is sent, but in
            # the same handler thread; give it a moment to finish.
            __import__("time").sleep(0.1)
            assert called["frc"] == 1
            assert called["update"]["message"]["text"] == "/frc"
        finally:
            server.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest notify/test_telegram.py::TestTelegramHandler -v
```

Expected: `AttributeError: module 'notify.telegram' has no attribute '_TelegramHandler'`.

- [ ] **Step 3: Write minimal implementation**

Append to `notify/telegram.py`:

```python
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from config.settings import (
    TELEGRAM_WEBHOOK_HOST,
    TELEGRAM_WEBHOOK_PORT,
    TELEGRAM_WEBHOOK_SECRET,
)


class _TelegramHandler(BaseHTTPRequestHandler):
    """Single-endpoint POST handler for Telegram updates.

    Order of operations in do_POST:
      1. Validate X-Telegram-Bot-Api-Secret-Token → 401 on mismatch.
      2. Read + parse JSON body → 400 on parse error.
      3. Validate update.message.chat.id == TELEGRAM_CHAT_ID → 200 + log on mismatch.
      4. Send 200 + flush (response on the wire BEFORE any slow work).
      5. Dispatch /frc synchronously in this same per-request thread.

    ThreadingHTTPServer assigns a fresh thread per request, so a slow /frc
    does not block subsequent updates.
    """

    server_version = "FyersAutoLogin/1.0"

    def log_message(self, fmt, *args):
        # Route BaseHTTPRequestHandler's stderr noise into our logger.
        logger.debug("webhook: " + fmt, *args)

    def _send(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()
        try:
            self.wfile.flush()
        except Exception:
            pass

    def do_POST(self):
        # 1. Secret header
        secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if not TELEGRAM_WEBHOOK_SECRET or secret != TELEGRAM_WEBHOOK_SECRET:
            logger.warning("webhook: rejected, bad secret header")
            self._send(401)
            return

        # 2. Parse body
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b""
            update = json.loads(raw.decode())
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"webhook: malformed JSON: {e}")
            self._send(400)
            return

        # 3. Chat-id allowlist
        try:
            incoming_chat_id = update["message"]["chat"]["id"]
        except (KeyError, TypeError):
            # Not a message update we care about (channel post, edit, etc.)
            self._send(200)
            return

        if str(incoming_chat_id) != str(TELEGRAM_CHAT_ID):
            logger.warning(f"webhook: rejected, chat_id {incoming_chat_id!r} != configured")
            self._send(200)
            return

        # 4. Send 200 NOW so Telegram doesn't time out / retry
        self._send(200)

        # 5. Dispatch /frc
        text = update.get("message", {}).get("text", "")
        if text == "/frc":
            try:
                _handle_frc(update)
            except Exception:
                logger.exception("webhook: _handle_frc raised")


def _handle_frc(update: dict) -> None:
    """Placeholder — implemented in Task 9.

    Pulled out as a module-level function so tests can monkeypatch it.
    """
    logger.warning("webhook: _handle_frc placeholder reached (Task 9 not implemented)")


def run_webhook_server(host: str = TELEGRAM_WEBHOOK_HOST, port: int = TELEGRAM_WEBHOOK_PORT) -> None:
    """Bind ThreadingHTTPServer and serve forever. Called from a daemon thread."""
    server = ThreadingHTTPServer((host, port), _TelegramHandler)
    logger.info(f"webhook: listening on {host}:{port}")
    server.serve_forever()
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest notify/test_telegram.py -v
```

Expected: All `TestTelegramHandler` cases pass + previous `TestSendMessage` cases still pass.

- [ ] **Step 5: Commit**

```bash
git add notify/telegram.py notify/test_telegram.py
git commit -m "feat(notify): add _TelegramHandler with secret + chat_id validation"
```

---

## Task 9: `notify/telegram.py` — `_handle_frc`

**Files:**
- Modify: `notify/telegram.py`
- Modify: `notify/test_telegram.py`

- [ ] **Step 1: Write the failing test**

Append to `notify/test_telegram.py`:

```python
class TestHandleFrc:
    def test_success_path_sends_three_messages(self, monkeypatch):
        from notify import telegram as t
        sent = []
        monkeypatch.setattr(t, "send_message",
                            lambda text, chat_id=None: sent.append((text, chat_id)) or True)
        monkeypatch.setattr(t, "force_full_login",
                            lambda: {"access_token": "a", "refresh_token": "r"})

        update = {"message": {"chat": {"id": 555}, "text": "/frc"}}
        t._handle_frc(update)

        assert len(sent) == 2  # "🔄 Forcing..." + "✅ Re-login complete..."
        assert "Forcing" in sent[0][0]
        assert "Re-login complete" in sent[1][0]
        # Replies route to the originating chat
        assert sent[0][1] == 555
        assert sent[1][1] == 555

    def test_failure_path_sends_failure_message(self, monkeypatch):
        from notify import telegram as t
        sent = []
        monkeypatch.setattr(t, "send_message",
                            lambda text, chat_id=None: sent.append((text, chat_id)) or True)
        monkeypatch.setattr(t, "force_full_login", lambda: {})

        update = {"message": {"chat": {"id": 555}, "text": "/frc"}}
        t._handle_frc(update)

        assert len(sent) == 2
        assert "Forcing" in sent[0][0]
        assert "Re-login failed" in sent[1][0]
        assert sent[1][1] == 555

    def test_exception_in_login_sends_internal_error(self, monkeypatch):
        from notify import telegram as t
        sent = []
        monkeypatch.setattr(t, "send_message",
                            lambda text, chat_id=None: sent.append((text, chat_id)) or True)

        def boom():
            raise RuntimeError("kaboom")
        monkeypatch.setattr(t, "force_full_login", boom)

        update = {"message": {"chat": {"id": 555}, "text": "/frc"}}
        t._handle_frc(update)  # must NOT raise

        assert any("Internal error" in text for text, _ in sent)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest notify/test_telegram.py::TestHandleFrc -v
```

Expected: tests fail because `_handle_frc` is the placeholder from Task 8 (only logs a warning, never calls send_message).

- [ ] **Step 3: Write minimal implementation**

In `notify/telegram.py`, replace the placeholder `_handle_frc` with the real implementation. Also add the import. The patch:

Find:
```python
from config.settings import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
```

Replace with:
```python
from config.settings import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from auth.force_login import force_full_login
```

Find:
```python
def _handle_frc(update: dict) -> None:
    """Placeholder — implemented in Task 9.

    Pulled out as a module-level function so tests can monkeypatch it.
    """
    logger.warning("webhook: _handle_frc placeholder reached (Task 9 not implemented)")
```

Replace with:
```python
def _handle_frc(update: dict) -> None:
    """Handle a /frc command: force a full TOTP login and reply to the originating chat."""
    chat_id = update["message"]["chat"]["id"]
    now_ist_str = _now_ist_str()
    send_message(f"🔄 Forcing Fyers re-login at {now_ist_str}...", chat_id=chat_id)
    try:
        tokens = force_full_login()
    except Exception:
        logger.exception("_handle_frc: force_full_login raised")
        send_message("❌ Internal error — check server logs", chat_id=chat_id)
        return
    if tokens.get("access_token"):
        send_message(f"✅ Re-login complete at {_now_ist_str()} — token valid 24h", chat_id=chat_id)
    else:
        send_message("❌ Re-login failed: see server logs for the failed step", chat_id=chat_id)
```

Add a helper near the top of the file (right after the imports):
```python
from datetime import datetime
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")


def _now_ist_str() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S IST")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest notify/test_telegram.py -v
```

Expected: all 14 notify tests pass.

- [ ] **Step 5: Commit**

```bash
git add notify/telegram.py notify/test_telegram.py
git commit -m "feat(notify): wire _handle_frc to force_full_login + chat reply"
```

---

## Task 10: `notify/telegram.py` — `register_bot` bootstrap

**Files:**
- Modify: `notify/telegram.py`
- Modify: `notify/test_telegram.py`

- [ ] **Step 1: Write the failing test**

Append to `notify/test_telegram.py`:

```python
class TestRegisterBot:
    def test_calls_setwebhook_and_setmycommands(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT")
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_URL", "https://example.com/tg")
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_SECRET", "SECRET")

        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append((req.full_url, json.loads(req.data.decode())))
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: None
            return resp

        with patch("notify.telegram.urlopen", side_effect=fake_urlopen):
            t.register_bot()

        urls = [c[0] for c in calls]
        assert any(u.endswith("/setWebhook") for u in urls)
        assert any(u.endswith("/setMyCommands") for u in urls)

        webhook_call = next(c for c in calls if c[0].endswith("/setWebhook"))
        assert webhook_call[1] == {
            "url": "https://example.com/tg",
            "secret_token": "SECRET",
        }

        commands_call = next(c for c in calls if c[0].endswith("/setMyCommands"))
        assert commands_call[1] == {
            "commands": [{"command": "frc", "description": "Force Fyers re-login"}]
        }

    def test_failure_is_non_fatal(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT")
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_URL", "https://example.com/tg")
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_SECRET", "SECRET")

        with patch("notify.telegram.urlopen", side_effect=URLError("down")):
            # Must not raise.
            t.register_bot()

    def test_skips_when_token_or_url_missing(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", None)
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_URL", None)
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_SECRET", None)
        # Should silently no-op (and not call urlopen).
        with patch("notify.telegram.urlopen") as m:
            t.register_bot()
            m.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest notify/test_telegram.py::TestRegisterBot -v
```

Expected: `AttributeError: module 'notify.telegram' has no attribute 'register_bot'`.

- [ ] **Step 3: Write minimal implementation**

Add to the imports at the top of `notify/telegram.py`:
```python
from config.settings import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_WEBHOOK_HOST,
    TELEGRAM_WEBHOOK_PORT,
    TELEGRAM_WEBHOOK_SECRET,
    TELEGRAM_WEBHOOK_URL,
)
```
(replacing the previous `from config.settings import ...` blocks; consolidate into one).

Append to `notify/telegram.py`:

```python
def register_bot() -> None:
    """One-shot startup: register webhook URL + advertise the /frc command.

    Failure is logged at WARNING and is non-fatal — the rest of the process
    starts regardless. If the webhook never gets registered, /frc simply
    won't reach us; restart the process once the public URL is live.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_WEBHOOK_URL:
        logger.warning("register_bot: TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_URL not set; skipping")
        return

    set_webhook_url = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    webhook_body = json.dumps({
        "url": TELEGRAM_WEBHOOK_URL,
        "secret_token": TELEGRAM_WEBHOOK_SECRET or "",
    }).encode()

    set_commands_url = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/setMyCommands"
    commands_body = json.dumps({
        "commands": [{"command": "frc", "description": "Force Fyers re-login"}],
    }).encode()

    headers = {"Content-Type": "application/json"}

    for url, body, label in [
        (set_webhook_url, webhook_body, "setWebhook"),
        (set_commands_url, commands_body, "setMyCommands"),
    ]:
        try:
            req = Request(url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                if 200 <= resp.status < 300:
                    logger.info(f"register_bot: {label} ✓")
                else:
                    logger.warning(f"register_bot: {label} HTTP {resp.status}")
        except (URLError, HTTPError) as e:
            logger.warning(f"register_bot: {label} failed: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest notify/test_telegram.py -v
```

Expected: all notify tests pass (17 total).

- [ ] **Step 5: Commit**

```bash
git add notify/telegram.py notify/test_telegram.py
git commit -m "feat(notify): add register_bot for setWebhook + setMyCommands"
```

---

## Task 11: `notify/__init__.py` — re-exports

**Files:**
- Modify: `notify/__init__.py`

- [ ] **Step 1: Replace `notify/__init__.py`**

```python
"""Telegram notifications + webhook for Fyers auto-login.

Public API:
  - send_message(text, chat_id=None) — POST to Telegram sendMessage.
  - register_bot() — one-shot setWebhook + setMyCommands.
  - run_webhook_server(host, port) — bind ThreadingHTTPServer and serve forever.
"""
from notify.telegram import (
    register_bot,
    run_webhook_server,
    send_message,
)

__all__ = ["register_bot", "run_webhook_server", "send_message"]
```

- [ ] **Step 2: Verify the public API is reachable**

Run:

```bash
uv run python -c "from notify import send_message, register_bot, run_webhook_server; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add notify/__init__.py
git commit -m "feat(notify): re-export public API"
```

---

## Task 12: `scheduler/scheduler.py` — `_run_scheduled_login` + `run_scheduler_loop`

**Files:**
- Modify: `scheduler/scheduler.py`
- Modify: `scheduler/test_scheduler.py`
- Modify: `scheduler/__init__.py`

- [ ] **Step 1: Write the failing test**

Append to `scheduler/test_scheduler.py`:

```python
from unittest.mock import patch


class TestRunScheduledLogin:
    def test_success_sends_success_message(self):
        with patch("scheduler.scheduler.force_full_login",
                   return_value={"access_token": "a"}) as m_login, \
             patch("scheduler.scheduler.send_message", return_value=True) as m_msg:
            from scheduler.scheduler import _run_scheduled_login
            _run_scheduled_login()
        m_login.assert_called_once_with()
        m_msg.assert_called_once()
        # The message text starts with the success marker.
        assert "✅" in m_msg.call_args.args[0]
        assert "successful" in m_msg.call_args.args[0].lower()

    def test_failure_sends_failure_message(self):
        with patch("scheduler.scheduler.force_full_login", return_value={}) as m_login, \
             patch("scheduler.scheduler.send_message", return_value=True) as m_msg:
            from scheduler.scheduler import _run_scheduled_login
            _run_scheduled_login()
        m_login.assert_called_once_with()
        m_msg.assert_called_once()
        assert "❌" in m_msg.call_args.args[0]
        assert "FAILED" in m_msg.call_args.args[0]

    def test_login_exception_caught_and_notified(self):
        with patch("scheduler.scheduler.force_full_login",
                   side_effect=RuntimeError("network")) as m_login, \
             patch("scheduler.scheduler.send_message", return_value=True) as m_msg:
            from scheduler.scheduler import _run_scheduled_login
            _run_scheduled_login()  # must not raise
        m_login.assert_called_once_with()
        assert m_msg.called
        assert "❌" in m_msg.call_args.args[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest scheduler/test_scheduler.py::TestRunScheduledLogin -v
```

Expected: `ImportError: cannot import name '_run_scheduled_login'` (or AttributeError).

- [ ] **Step 3: Write minimal implementation**

Append to `scheduler/scheduler.py`:

```python
import logging
import time as _time

from auth.auth import load_token
from auth.force_login import force_full_login
from config.settings import SCHEDULER_TRIGGER_TIME
from notify.telegram import send_message

logger = logging.getLogger(__name__)

_DEFAULT_TRIGGER = time(9, 13)


def _now_ist_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _parse_trigger_time(value: str) -> time:
    """Parse 'HH:MM' → time. Falls back to 09:13 on any parse error (logged)."""
    try:
        hh, mm = value.split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError) as e:
        logger.error(f"SCHEDULER_TRIGGER_TIME bad format {value!r}: {e}; using 09:13")
        return _DEFAULT_TRIGGER


def _run_scheduled_login() -> None:
    """Run the scheduled login and send a Telegram notification.

    Caught: any exception from force_full_login. We always notify and we
    never let the loop die.
    """
    try:
        tokens = force_full_login()
    except Exception as e:
        logger.exception("_run_scheduled_login: force_full_login raised")
        send_message(f"❌ Fyers scheduled login FAILED at {_now_ist_str()} — {e}")
        return
    if tokens.get("access_token"):
        send_message(f"✅ Fyers login successful at {_now_ist_str()} — token valid 24h")
    else:
        send_message(f"❌ Fyers scheduled login FAILED at {_now_ist_str()} — see server logs")


def _cached_token_date():
    """Return the IST date of the cached token, or None if no/invalid cache."""
    cached = load_token()
    ts = cached.get("timestamp")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).astimezone(IST).date()
    except (ValueError, TypeError):
        return None


def run_scheduler_loop() -> None:
    """Daemon thread entry. Catch-up on startup, then loop forever.

    The loop never raises out — every error inside _run_scheduled_login
    is caught and reported. The thread is daemon, so it dies with the
    process; the gRPC main thread is the lifetime owner.
    """
    trigger_time = _parse_trigger_time(SCHEDULER_TRIGGER_TIME)
    logger.info(f"scheduler: started, trigger {trigger_time.isoformat(timespec='minutes')} IST")

    # Catch-up on boot
    now = datetime.now(IST)
    if should_run_catchup(now, trigger_time, _cached_token_date()):
        logger.info("scheduler: catch-up triggered on startup")
        _run_scheduled_login()

    while True:
        now = datetime.now(IST)
        target = next_trigger_at(now, trigger_time)
        sleep_s = (target - now).total_seconds()
        if sleep_s > 0:
            logger.info(f"scheduler: sleeping {sleep_s:.0f}s until {target.isoformat()}")
            _time.sleep(sleep_s)
        _run_scheduled_login()
```

Replace `scheduler/__init__.py` with:

```python
"""Daily 09:13 IST weekday auto-login scheduler.

Public API:
  - run_scheduler_loop() — daemon thread entry; catches up on startup, then loops forever.
  - is_trading_day(d) — Mon–Fri = True, Sat/Sun = False.
  - next_trigger_at(now, trigger_time) — pure function for next trigger datetime.
"""
from scheduler.scheduler import (
    is_trading_day,
    next_trigger_at,
    run_scheduler_loop,
    should_run_catchup,
)

__all__ = ["is_trading_day", "next_trigger_at", "run_scheduler_loop", "should_run_catchup"]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest scheduler/test_scheduler.py -v
```

Expected: all scheduler tests pass.

- [ ] **Step 5: Verify full test suite still passes**

Run:

```bash
uv run pytest -v
```

Expected: all tests pass across `scheduler/`, `notify/`, and `auth/`.

- [ ] **Step 6: Commit**

```bash
git add scheduler/scheduler.py scheduler/test_scheduler.py scheduler/__init__.py
git commit -m "feat(scheduler): add run_scheduler_loop with catchup + notification"
```

---

## Task 13: `run_grpc.py` — wire bootstrap + daemon threads

**Files:**
- Modify: `run_grpc.py`

This task has no automated test — it's a 5-line edit to a 12-line file, exercised by the manual smoke checklist in Task 14.

- [ ] **Step 1: Replace `run_grpc.py`**

```python
"""Entry point: start the gRPC server + auto-login scheduler + Telegram webhook.

Three concurrent components inside a single process:
  - main thread: gRPC server (blocks forever)
  - daemon thread: scheduler loop (Mon–Fri 09:13 IST auto-login)
  - daemon thread: Telegram webhook HTTP server (/frc command)

Plus a one-shot bootstrap that registers the webhook URL with Telegram and
advertises the /frc command. The bootstrap is best-effort: failure is
logged but does not block startup.
"""
import logging
import threading

import config.settings as settings
import notify
import scheduler
from grpc_service.server import serve

logger = logging.getLogger(__name__)


def _start_daemon(target, name, *args):
    t = threading.Thread(target=target, args=args, name=name, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s]: %(message)s",
    )

    # 1. One-shot Telegram bootstrap (non-fatal).
    notify.register_bot()

    # 2. Telegram webhook server thread.
    _start_daemon(
        notify.run_webhook_server,
        "telegram-webhook",
        settings.TELEGRAM_WEBHOOK_HOST,
        settings.TELEGRAM_WEBHOOK_PORT,
    )

    # 3. Scheduler thread (catch-up on boot, then daily 09:13 IST loop).
    _start_daemon(scheduler.run_scheduler_loop, "scheduler")

    # 4. gRPC server (blocks the main thread).
    serve(host=settings.GRPC_HOST, port=settings.GRPC_PORT)
```

- [ ] **Step 2: Verify imports and syntax**

Run:

```bash
uv run python -c "import run_grpc; print('imports ok')"
```

Expected: `imports ok` (the `if __name__ == '__main__'` block does not execute on import).

- [ ] **Step 3: Run the full test suite to confirm no regressions**

Run:

```bash
uv run pytest -v
```

Expected: all tests still pass.

- [ ] **Step 4: Commit**

```bash
git add run_grpc.py
git commit -m "feat: wire scheduler + telegram webhook into run_grpc entry"
```

---

## Task 14: `.env` documentation + manual smoke test

**Files:**
- Modify: `.env` (user-facing; the user pastes their own values)

This task is a checklist for the human operator. No code changes.

- [ ] **Step 1: Add the new env vars to `.env`**

Append the following block to `.env` (replace each `<...>` with a real value):

```
# Telegram bot — auto-login notifications + /frc command
TELEGRAM_BOT_TOKEN=<bot token from @BotFather>
TELEGRAM_CHAT_ID=<numeric chat id, e.g. 123456789>
TELEGRAM_WEBHOOK_URL=<full https URL Telegram POSTs to, e.g. https://example.com/telegram>
TELEGRAM_WEBHOOK_HOST=0.0.0.0
TELEGRAM_WEBHOOK_PORT=8080
TELEGRAM_WEBHOOK_SECRET=<random 32+ char string, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`>

# Optional: override the daily auto-login trigger (default 09:13 IST)
# SCHEDULER_TRIGGER_TIME=09:13
```

`TELEGRAM_CHAT_ID` is the numeric chat ID where the bot will send notifications and from which `/frc` is accepted. Easiest way to find it: send a message to your bot from your Telegram account, then `curl https://api.telegram.org/bot<TOKEN>/getUpdates` — the chat ID appears as `chat.id`.

- [ ] **Step 2: Start the server**

Run:

```bash
uv run python run_grpc.py
```

Expected log lines (in order):
- `register_bot: setWebhook ✓`
- `register_bot: setMyCommands ✓`
- `webhook: listening on 0.0.0.0:8080`
- `scheduler: started, trigger 09:13 IST`
- `scheduler: sleeping <N>s until <next trigger>` (or `scheduler: catch-up triggered on startup` if you start past 09:13 on a weekday with a stale cache)
- `gRPC server listening on 0.0.0.0:50051`

If startup catch-up fires you should also see a Telegram message: `✅ Fyers login successful at <time> IST — token valid 24h`.

- [ ] **Step 3: Smoke test webhook secret enforcement**

In a second terminal:

```bash
curl -i -X POST -H "Content-Type: application/json" -d '{"message":{"chat":{"id":1},"text":"/frc"}}' http://localhost:8080/
```

Expected: `HTTP/1.0 401 Unauthorized` (no secret header).

Now with the secret:

```bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: $TELEGRAM_WEBHOOK_SECRET" \
  -d '{"message":{"chat":{"id":1},"text":"/frc"}}' \
  http://localhost:8080/
```

Expected: `HTTP/1.0 200 OK` BUT no Telegram reply (chat ID 1 doesn't match `TELEGRAM_CHAT_ID`). Server log: `webhook: rejected, chat_id 1 != configured`.

- [ ] **Step 4: Smoke test `/frc` end-to-end**

In Telegram, send `/frc` to your bot. Expected within ~10 seconds:
- `🔄 Forcing Fyers re-login at <time IST>...`
- `✅ Re-login complete at <time IST> — token valid 24h`

Server logs: `force_full_login: starting full TOTP flow` → `Step 1` → `Step 2` → … → `Step 5: validate_auth_code ✓` → `force_full_login: success`.

- [ ] **Step 5: Smoke test scheduler weekend skip**

(Optional — only if you want to verify weekend behavior without waiting.)

Temporarily set your system clock to a Saturday at any time, restart `run_grpc.py`. Expected:
- No catchup login (it's a non-trading day).
- `scheduler: sleeping <N>s until 2026-MM-DD 09:13:00+05:30` where MM-DD is the next Monday.
- No Telegram message.

Restore your clock.

- [ ] **Step 6: Final commit (no code, but mark the task complete)**

```bash
git status
```

Expected: clean working tree (the `.env` file is gitignored). No commit needed for this task — it's just operational verification.

---

## Self-Review Notes

- **Spec coverage:**
  - Architecture (3 daemon-style components inside `run_grpc.py`) → Tasks 12, 13.
  - IST handling → Tasks 4, 5, 12 (`IST = ZoneInfo("Asia/Kolkata")` everywhere).
  - `is_trading_day`, `next_trigger_at`, `should_run_catchup` → Tasks 3, 4, 5.
  - `run_scheduler_loop` w/ catch-up → Task 12.
  - `send_message` → Task 7.
  - `_TelegramHandler` (secret + chat_id + 200-then-work) → Task 8.
  - `_handle_frc` → Task 9.
  - `register_bot` → Task 10.
  - `force_full_login` w/ Lock → Task 6.
  - Settings env vars → Task 2.
  - `run_grpc.py` wiring → Task 13.
  - `.env` doc + smoke → Task 14.
  - Notification policy (success/failure for scheduler; 🔄/✅/❌ for /frc; quiet on fresh-cache catchup) → Tasks 9, 12.
  - Error handling table — every row has a corresponding test or behavior in the implementation tasks.
- **Placeholder scan:** none of the bad patterns (TBD, "implement later", "similar to Task N", "add validation"). All steps include exact code or commands.
- **Type consistency:** `force_full_login` returns `dict` everywhere. `send_message(text, chat_id=None)` signature matches across `_handle_frc`, `_run_scheduled_login`, and the `notify/__init__.py` re-export. `next_trigger_at(now, trigger_time)` and `should_run_catchup(now, trigger_time, cached_token_date)` signatures are consistent across tests and implementation.
