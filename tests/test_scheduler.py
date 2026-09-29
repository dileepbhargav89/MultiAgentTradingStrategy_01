"""Unit tests for TimingScheduler (Sprint 10)."""

import math
from datetime import datetime, timezone
import pytest
from core.scheduler import TimingScheduler


def test_timeframe_seconds_lookup():
    assert TimingScheduler.get_timeframe_seconds("15m") == 900
    assert TimingScheduler.get_timeframe_seconds("1h") == 3600
    assert TimingScheduler.get_timeframe_seconds("4h") == 14400
    assert TimingScheduler.get_timeframe_seconds("1d") == 86400

    with pytest.raises(ValueError):
        TimingScheduler.get_timeframe_seconds("invalid_tf")


def test_seconds_until_next_candle():
    # Freeze time at 12:05:00 UTC (300 seconds into a 15m candle)
    fixed_time = datetime(2026, 9, 25, 12, 5, 0, tzinfo=timezone.utc)
    # Remaining in 15m candle = 900 - 300 = 600s + 1.5s buffer = 601.5s
    rem = TimingScheduler.seconds_until_next_candle("15m", now=fixed_time, buffer_seconds=1.5)
    assert rem == 601.5

    # Freeze time at 12:14:59 UTC (1s remaining in 15m candle)
    fixed_time_end = datetime(2026, 9, 25, 12, 14, 59, tzinfo=timezone.utc)
    rem_end = TimingScheduler.seconds_until_next_candle("15m", now=fixed_time_end, buffer_seconds=1.0)
    assert rem_end == 2.0


def test_is_retrain_due():
    # If last retrain is None, retrain is immediately due
    assert TimingScheduler.is_retrain_due(None, interval_hours=24) is True

    now = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
    # 10 hours ago -> not due for 24h interval
    recent = datetime(2026, 9, 25, 2, 0, 0, tzinfo=timezone.utc)
    assert TimingScheduler.is_retrain_due(recent, interval_hours=24, now=now) is False

    # 25 hours ago -> due!
    stale = datetime(2026, 9, 24, 11, 0, 0, tzinfo=timezone.utc)
    assert TimingScheduler.is_retrain_due(stale, interval_hours=24, now=now) is True


def test_get_current_candle_timestamp():
    test_time = datetime(2026, 9, 25, 12, 7, 34, tzinfo=timezone.utc)
    candle_start = TimingScheduler.get_current_candle_timestamp("15m", now=test_time)
    assert candle_start == datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)

    candle_start_1h = TimingScheduler.get_current_candle_timestamp("1h", now=test_time)
    assert candle_start_1h == datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
