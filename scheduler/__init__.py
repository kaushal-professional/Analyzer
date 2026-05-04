"""Daily 09:13 IST weekday auto-login scheduler.

Public API:
  - run_scheduler_loop() — daemon thread entry; catches up on startup, then loops forever.
  - is_trading_day(d) — Mon–Fri = True, Sat/Sun = False.
  - next_trigger_at(now, trigger_time) — pure function for next trigger datetime.
  - should_run_catchup(now, trigger_time, cached_token_date) — boot-time catch-up check.
"""
from scheduler.scheduler import (
    is_trading_day,
    next_trigger_at,
    run_scheduler_loop,
    should_run_catchup,
)

__all__ = ["is_trading_day", "next_trigger_at", "run_scheduler_loop", "should_run_catchup"]
