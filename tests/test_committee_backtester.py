"""Unit tests for TearSheetCalculator and MultiAgentCommitteeBacktester (Sprint 12)."""

from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import pytest

from engine.committee_backtester import MultiAgentCommitteeBacktester
from models.tear_sheet import TearSheetCalculator, TearSheetReport


def test_tear_sheet_calculator_positive_drift():
    """Validates metrics calculation on a consistently profitable equity series."""
    equities = [10000.0, 10100.0, 10250.0, 10200.0, 10400.0, 10500.0]
    trades = [
        {"realized_pnl_usd": 100.0, "fee_paid_usd": 1.0, "reason": "TP1"},
        {"realized_pnl_usd": 150.0, "fee_paid_usd": 1.0, "reason": "TP2"},
        {"realized_pnl_usd": -50.0, "fee_paid_usd": 1.0, "reason": "SL"},
        {"realized_pnl_usd": 200.0, "fee_paid_usd": 1.0, "reason": "TP1"},
        {"realized_pnl_usd": 100.0, "fee_paid_usd": 1.0, "reason": "TP1"},
    ]

    report = TearSheetCalculator.compute(
        equity_series=equities,
        trade_history=trades,
        initial_equity=10000.0,
        active_bars=5,
    )

    assert isinstance(report, TearSheetReport)
    assert report.total_return_usd == 500.0
    assert report.total_return_pct == 0.05
    assert report.total_trades == 5
    assert report.winning_trades == 4
    assert report.losing_trades == 1
    assert report.win_rate_pct == 0.80
    assert report.profit_factor > 1.0
    assert report.total_fees_paid_usd == 5.0
    assert report.max_drawdown_pct < 0.01  # Small 50 usd dip


def test_backtester_insufficient_warmup_error():
    """Ensures backtester raises ValueError when candles are insufficient for warmup."""
    backtester = MultiAgentCommitteeBacktester(warmup_candles=100)
    df_short = pd.DataFrame({
        "timestamp": [datetime.now(timezone.utc)],
        "open": [70000.0],
        "high": [70100.0],
        "low": [69900.0],
        "close": [70050.0],
        "volume": [10.0],
    })

    with pytest.raises(ValueError, match="Insufficient candles"):
        import asyncio
        asyncio.run(backtester.run(df_short))


@pytest.mark.asyncio
async def test_committee_backtester_execution():
    """Runs a mini chronological walk-forward simulation."""
    np.random.seed(42)
    n = 230
    timestamps = [datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * i) for i in range(n)]
    returns = np.random.normal(0.0001, 0.002, n)
    prices = 70000.0 * np.cumprod(1.0 + returns)

    df_15m = pd.DataFrame({
        "timestamp": timestamps,
        "open": prices * 0.999,
        "high": prices * 1.002,
        "low": prices * 0.998,
        "close": prices,
        "volume": np.random.uniform(50, 200, n),
    })

    backtester = MultiAgentCommitteeBacktester(
        symbol="BTC/USDT",
        initial_equity=10000.0,
        warmup_candles=200,
        retrain_interval_bars=50,
    )

    report, df_equity = await backtester.run(df_15m)

    assert isinstance(report, TearSheetReport)
    assert len(df_equity) == (n - 200) + 1
    assert "equity" in df_equity.columns
    assert "drawdown" in df_equity.columns
    assert report.final_equity > 0.0
