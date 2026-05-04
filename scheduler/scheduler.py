"""Daily 09:13 IST weekday auto-login scheduler.

Runs as a daemon thread inside run_grpc.py. Computes the next IST trigger
(default 09:13, configurable via SCHEDULER_TRIGGER_TIME), sleeps until then,
fires force_full_login(), and repeats. Skips weekends.
"""
import logging
import time as _time
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from auth.auth import load_token
from auth.force_login import force_full_login
from config.settings import SCHEDULER_TRIGGER_TIME
from notify.telegram import send_message

IST = ZoneInfo("Asia/Kolkata")

logger = logging.getLogger(__name__)


def is_trading_day(d: date) -> bool:
    """True for Mon–Fri (NSE weekday). Sat/Sun are non-trading days."""
    return d.weekday() < 5  # Mon=0 ... Sun=6


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


_DEFAULT_TRIGGER = time(9, 13)


def _now_ist_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _parse_trigger_time(value: str) -> time:
    """Parse 'HH:MM' or 'HH:MM:SS' → time. Falls back to 09:13 on any parse error (logged)."""
    try:
        return time.fromisoformat(value)
    except (ValueError, TypeError) as e:
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

    # Catch-up on boot. Guarded so any IO error (PermissionError, OSError on
    # the token file, etc.) doesn't silently kill the daemon thread before
    # it ever enters the main loop.
    try:
        now = datetime.now(IST)
        if should_run_catchup(now, trigger_time, _cached_token_date()):
            logger.info("scheduler: catch-up triggered on startup")
            _run_scheduled_login()
    except Exception:
        logger.exception("scheduler: startup phase failed; continuing to loop")

    while True:
        now = datetime.now(IST)
        target = next_trigger_at(now, trigger_time)
        sleep_s = (target - now).total_seconds()
        if sleep_s > 0:
            logger.info(f"scheduler: sleeping {sleep_s:.0f}s until {target.isoformat()}")
            _time.sleep(sleep_s)
        _run_scheduled_login()
