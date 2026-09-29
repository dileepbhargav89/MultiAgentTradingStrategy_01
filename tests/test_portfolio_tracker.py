"""Unit tests for PortfolioTracker (Sprint 7)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from models.portfolio_tracker import PortfolioTracker


@pytest.fixture
def temp_tracker(tmp_path):
    """Provides a fresh PortfolioTracker with an isolated temp JSON state file."""
    state_file = tmp_path / "test_portfolio_state.json"
    tracker = PortfolioTracker(
        initial_equity=10000.0,
        daily_loss_limit_pct=0.03,
        weekly_loss_limit_pct=0.07,
        max_consecutive_losses=4,
        cooldown_duration_hours=2.0,
        state_file_path=str(state_file),
    )
    return tracker


def test_initial_portfolio_state(temp_tracker):
    assert temp_tracker.mtm_equity == 10000.0
    assert temp_tracker.high_water_mark == 10000.0
    assert temp_tracker.drawdown_pct == 0.0
    assert temp_tracker.daily_loss_pct == 0.0
    assert temp_tracker.consecutive_losses == 0
    assert not temp_tracker.is_cooldown_active


def test_unrealized_pnl_and_drawdown(temp_tracker):
    # Simulated unrealized loss of -$500
    temp_tracker.update_unrealized_pnl(unrealized_pnl=-500.0, open_exposure_usd=3000.0)
    assert temp_tracker.mtm_equity == 9500.0
    assert temp_tracker.drawdown_pct == pytest.approx(0.05, rel=1e-3)
    assert temp_tracker.current_exposure_pct == pytest.approx(3000.0 / 9500.0, rel=1e-3)

    # Simulated unrealized gain to new HWM
    temp_tracker.update_unrealized_pnl(unrealized_pnl=1200.0, open_exposure_usd=4000.0)
    assert temp_tracker.mtm_equity == 11200.0
    assert temp_tracker.high_water_mark == 11200.0
    assert temp_tracker.drawdown_pct == 0.0


def test_record_winning_trade(temp_tracker):
    temp_tracker.consecutive_losses = 2
    temp_tracker.record_trade_result(net_pnl=400.0)

    assert temp_tracker.current_cash == 10400.0
    assert temp_tracker.high_water_mark == 10400.0
    assert temp_tracker.consecutive_losses == 0  # Streak reset


def test_consecutive_losses_and_cooldown(temp_tracker):
    now = datetime.now(timezone.utc)
    for i in range(3):
        temp_tracker.record_trade_result(net_pnl=-50.0, timestamp=now)
        assert temp_tracker.consecutive_losses == i + 1
        assert not temp_tracker.is_cooldown_active

    # 4th consecutive loss triggers cooldown
    temp_tracker.record_trade_result(net_pnl=-50.0, timestamp=now)
    assert temp_tracker.consecutive_losses == 4
    assert temp_tracker.is_cooldown_active
    assert temp_tracker.cooldown_until > now

    # Circuit breaker should report cooldown
    tripped, reason = temp_tracker.get_circuit_breaker_status()
    assert tripped is True
    assert "CONSECUTIVE_LOSS_COOLDOWN" in reason


def test_daily_loss_limit_circuit_breaker(temp_tracker):
    # Daily starting baseline is 10,000. 3% is $300.
    temp_tracker.record_trade_result(net_pnl=-350.0)
    assert temp_tracker.daily_loss_pct >= 0.03

    tripped, reason = temp_tracker.get_circuit_breaker_status()
    assert tripped is True
    assert "DAILY_LOSS_LIMIT_BREACHED" in reason


def test_weekly_loss_limit_circuit_breaker(temp_tracker):
    # Weekly starting baseline is 10,000. 7% is $700.
    # Distribute losses across 3 days in the same week so daily loss stays <3%
    # Use fixed mid-week days (Tue, Wed, Thu) in the same ISO week to prevent weekend boundary shifts
    day1 = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    day3 = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)

    temp_tracker.update_calendar_time(day1)
    temp_tracker.record_trade_result(net_pnl=-250.0, timestamp=day1)  # 2.5% loss on day 1

    temp_tracker.update_calendar_time(day2)
    temp_tracker.record_trade_result(net_pnl=-250.0, timestamp=day2)  # 2.56% loss on day 2

    temp_tracker.update_calendar_time(day3)
    temp_tracker.record_trade_result(net_pnl=-250.0, timestamp=day3)  # 2.63% loss on day 3

    assert temp_tracker.daily_loss_pct < 0.03  # Today's daily loss is < 3%
    assert temp_tracker.weekly_loss_pct >= 0.07  # Cumulative weekly loss is 7.5% >= 7%

    tripped, reason = temp_tracker.get_circuit_breaker_status()
    assert tripped is True
    assert "WEEKLY_LOSS_LIMIT_BREACHED" in reason


def test_critical_drawdown_circuit_breaker(temp_tracker):
    # Drawdown of 11% from HWM
    temp_tracker.record_trade_result(net_pnl=-1100.0)
    assert temp_tracker.drawdown_pct >= 0.10

    tripped, reason = temp_tracker.get_circuit_breaker_status()
    assert tripped is True
    assert "CRITICAL_DRAWDOWN_LIMIT" in reason


def test_state_persistence_and_reload(tmp_path):
    state_file = tmp_path / "persist_test.json"
    tracker1 = PortfolioTracker(initial_equity=10000.0, state_file_path=str(state_file))

    # Perform mutations
    tracker1.record_trade_result(net_pnl=500.0)   # Cash = 10,500, HWM = 10,500
    tracker1.record_trade_result(net_pnl=-200.0)  # Cash = 10,300, 1 loss
    tracker1.save_state()

    assert state_file.exists()

    # Create fresh instance pointing to the same file
    tracker2 = PortfolioTracker(initial_equity=10000.0, state_file_path=str(state_file))
    assert tracker2.current_cash == 10300.0
    assert tracker2.high_water_mark == 10500.0
    assert tracker2.consecutive_losses == 1
    assert tracker2.drawdown_pct == pytest.approx((10500 - 10300) / 10500, rel=1e-3)


def test_recovery_persists_across_restart(tmp_path):
    from datetime import datetime, timezone, timedelta

    state_file = tmp_path / "recovery_state.json"
    tracker1 = PortfolioTracker(initial_equity=10000.0, state_file_path=str(state_file))
    test_time = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    tracker1.recovery_entered_at = test_time
    tracker1.consecutive_recovery_wins = 3
    tracker1.save_state()

    # Reload in a new instance
    tracker2 = PortfolioTracker(initial_equity=10000.0, state_file_path=str(state_file))
    assert tracker2.recovery_entered_at == test_time
    assert tracker2.consecutive_recovery_wins == 3

