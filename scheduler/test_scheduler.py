"""Unit tests for scheduler.scheduler."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from scheduler.scheduler import (
    IST,
    is_trading_day,
    next_trigger_at,
    should_run_catchup,
)

UTC = ZoneInfo("UTC")


def _ist(year, month, day, hh, mm):
    return datetime(year, month, day, hh, mm, tzinfo=IST)


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
        # If now == trigger to the minute, the *next* trigger is tomorrow's.
        now = _ist(2026, 5, 4, 9, 13)
        result = next_trigger_at(now, self.TRIGGER)
        assert result == _ist(2026, 5, 5, 9, 13)

    def test_utc_input_converts_to_ist(self):
        # 2026-05-04 03:43 UTC == 2026-05-04 09:13 IST.
        # An input one minute earlier (03:42 UTC = 09:12 IST) should fire today at 09:13 IST.
        now_utc = datetime(2026, 5, 4, 3, 42, tzinfo=UTC)
        result = next_trigger_at(now_utc, self.TRIGGER)
        assert result == _ist(2026, 5, 4, 9, 13)


class TestShouldRunCatchup:
    TRIGGER = time(9, 13)

    def test_weekday_after_trigger_no_cache_runs(self):
        now = _ist(2026, 5, 4, 10, 0)
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=None) is True

    def test_weekday_after_trigger_cache_today_skips(self):
        now = _ist(2026, 5, 4, 10, 0)
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=date(2026, 5, 4)) is False

    def test_weekday_after_trigger_cache_yesterday_runs(self):
        now = _ist(2026, 5, 4, 10, 0)
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=date(2026, 5, 3)) is True

    def test_weekday_before_trigger_skips(self):
        now = _ist(2026, 5, 4, 8, 0)
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=None) is False
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=date(2026, 5, 3)) is False

    def test_weekday_exactly_at_trigger_no_cache_runs(self):
        # Mirror the next_trigger_at boundary test — at-trigger should fire catchup.
        now = _ist(2026, 5, 4, 9, 13)
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=None) is True

    def test_saturday_skips(self):
        now = _ist(2026, 5, 9, 10, 0)
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=None) is False
        assert should_run_catchup(now, self.TRIGGER, cached_token_date=date(2026, 5, 8)) is False

    def test_utc_input_converts_to_ist(self):
        # 2026-05-04 04:30 UTC == 2026-05-04 10:00 IST → after trigger, no cache → True.
        now_utc = datetime(2026, 5, 4, 4, 30, tzinfo=UTC)
        assert should_run_catchup(now_utc, self.TRIGGER, cached_token_date=None) is True


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


class TestParseTriggerTime:
    def test_hh_mm_format(self):
        from scheduler.scheduler import _parse_trigger_time
        assert _parse_trigger_time("09:13") == time(9, 13)

    def test_hh_mm_ss_format_accepted(self):
        # Operators sometimes write the trailing :00 seconds; accept it cleanly
        # rather than silently falling back to the default.
        from scheduler.scheduler import _parse_trigger_time
        assert _parse_trigger_time("09:13:00") == time(9, 13)

    def test_garbage_falls_back_to_default(self):
        from scheduler.scheduler import _parse_trigger_time, _DEFAULT_TRIGGER
        assert _parse_trigger_time("not-a-time") == _DEFAULT_TRIGGER

    def test_none_falls_back_to_default(self):
        from scheduler.scheduler import _parse_trigger_time, _DEFAULT_TRIGGER
        assert _parse_trigger_time(None) == _DEFAULT_TRIGGER  # type: ignore[arg-type]


class TestRunSchedulerLoop:
    def test_catchup_runs_when_should_run_catchup_true(self):
        # Smoke test for the loop orchestration. Stops the infinite loop by
        # making _time.sleep raise after the first iteration's pre-sleep.
        from scheduler import scheduler as s

        class _StopLoop(BaseException):
            """Use BaseException so the loop's exception handlers don't catch it."""

        with patch.object(s, "should_run_catchup", return_value=True), \
             patch.object(s, "_run_scheduled_login") as m_run, \
             patch.object(s, "_time") as m_time, \
             patch.object(s, "_cached_token_date", return_value=None):
            # Catch-up fires (call 1), then loop body computes target and sleeps;
            # we make sleep raise to break the infinite loop.
            m_time.sleep.side_effect = _StopLoop()
            try:
                s.run_scheduler_loop()
            except _StopLoop:
                pass
        # Catch-up call only — loop body fires _run_scheduled_login AFTER sleep,
        # but we raised inside sleep so the second call never happens.
        assert m_run.call_count == 1

    def test_no_catchup_when_should_run_catchup_false(self):
        from scheduler import scheduler as s

        class _StopLoop(BaseException):
            pass

        with patch.object(s, "should_run_catchup", return_value=False), \
             patch.object(s, "_run_scheduled_login") as m_run, \
             patch.object(s, "_time") as m_time, \
             patch.object(s, "_cached_token_date", return_value=None):
            m_time.sleep.side_effect = _StopLoop()
            try:
                s.run_scheduler_loop()
            except _StopLoop:
                pass
        # No catch-up; loop reaches sleep on first iteration and we abort there.
        assert m_run.call_count == 0

    def test_startup_phase_exception_does_not_kill_thread(self):
        # If _cached_token_date raises (PermissionError on the cache file, etc.),
        # the loop should log and continue rather than die silently.
        from scheduler import scheduler as s

        class _StopLoop(BaseException):
            pass

        with patch.object(s, "_cached_token_date", side_effect=PermissionError("locked")), \
             patch.object(s, "_run_scheduled_login") as m_run, \
             patch.object(s, "_time") as m_time:
            m_time.sleep.side_effect = _StopLoop()
            try:
                s.run_scheduler_loop()
            except _StopLoop:
                pass
        # Startup phase swallowed the exception; we reached the loop and the
        # sleep that aborts it. _run_scheduled_login was never invoked because
        # the catchup branch never executed (exception thrown before it).
        assert m_run.call_count == 0
