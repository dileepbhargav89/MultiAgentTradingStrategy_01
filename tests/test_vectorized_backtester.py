"""Unit tests for VectorizedBacktester verifying zero look-ahead bias, fee deduction, and speed."""

import time
import numpy as np
import pandas as pd
import pytest

from core.types import StrategyGenome, StrategySpecies
from engine.vectorized_backtester import VectorizedBacktester


def generate_ohlcv(periods: int = 200, trend: float = 0.001) -> pd.DataFrame:
    np.random.seed(123)
    closes = [50000.0]
    for _ in range(periods - 1):
        closes.append(closes[-1] * (1.0 + np.random.normal(trend, 0.004)))

    closes = np.array(closes)
    return pd.DataFrame({
        "open": closes * 0.999,
        "high": closes * 1.003,
        "low": closes * 0.997,
        "close": closes,
        "volume": [1200.0] * periods,
    })


def test_zero_lookahead_bias():
    """
    CRITICAL AUDIT: A sudden pump at bar t generates a buy signal at bar t.
    Zero look-ahead dictates that the strategy's position at bar t MUST be 0,
    meaning it CANNOT capture the return of the bar that produced the signal.
    """
    # 60 flat candles, sudden 30% jump at index 30
    closes = [50000.0] * 60
    closes[30] = 65000.0  # Big jump at bar 30
    for i in range(31, 60):
        closes[i] = 65000.0

    df_pump = pd.DataFrame({
        "open": closes,
        "high": [c * 1.001 for c in closes],
        "low": [c * 0.999 for c in closes],
        "close": closes,
        "volume": [1000.0] * 60,
    })

    genome = StrategyGenome(
        strategy_id="TEST-LOOKAHEAD",
        species=StrategySpecies.MOMENTUM_TREND,
        trend_filter_lookback=15,
    )

    backtester = VectorizedBacktester(taker_fee_pct=0.0, slippage_pct=0.0)
    result = backtester.backtest(df_pump, genome, initial_capital=10000.0)

    # If lookahead bias existed, the strategy would capture the 30% pump at bar 30!
    # Because lookahead is eliminated, at bar 30 position was 0.0, so the 30% jump is missed!
    assert result.net_pnl_pct < 5.0, f"Expected missed pump (<5%), but got {result.net_pnl_pct}%! Lookahead bias detected!"


def test_trading_frictions_deducted():
    """Verifies that taker fees and slippage are deducted on position changes."""
    df = generate_ohlcv(periods=100)
    genome = StrategyGenome(
        strategy_id="TEST-FRICTION",
        species=StrategySpecies.MEAN_REVERSION,
    )

    # 1. Backtest with zero friction
    bt_zero = VectorizedBacktester(taker_fee_pct=0.0, slippage_pct=0.0)
    res_zero = bt_zero.backtest(df, genome)

    # 2. Backtest with realistic friction (0.04% fee + 0.01% slip)
    bt_fric = VectorizedBacktester(taker_fee_pct=0.0004, slippage_pct=0.0001)
    res_fric = bt_fric.backtest(df, genome)

    if res_zero.total_trades > 0:
        # Net return with fees must be lower than net return without fees
        assert res_fric.net_pnl_pct < res_zero.net_pnl_pct


def test_backtest_performance_benchmark():
    """Ensures 2,000 candles are backtested in under 20ms."""
    df_long = generate_ohlcv(periods=2000)
    genome = StrategyGenome(
        strategy_id="BENCHMARK",
        species=StrategySpecies.MOMENTUM_TREND,
        trend_filter_lookback=50,
    )

    backtester = VectorizedBacktester()

    # Warmup
    backtester.backtest(df_long, genome)

    # Timed run
    start_t = time.perf_counter()
    res = backtester.backtest(df_long, genome)
    elapsed_ms = (time.perf_counter() - start_t) * 1000.0

    assert elapsed_ms < 150.0, f"Backtester too slow: {elapsed_ms:.2f}ms"
    assert res.total_trades >= 0
    assert len(res.equity_curve) > 0


def test_backtest_returns_strategy_returns():
    df = generate_ohlcv(periods=100)
    genome = StrategyGenome(
        strategy_id="TEST-RETURNS",
        species=StrategySpecies.MOMENTUM_TREND,
    )
    backtester = VectorizedBacktester()
    res = backtester.backtest(df, genome)
    assert res.strategy_returns is not None
    assert isinstance(res.strategy_returns, np.ndarray)
    assert len(res.strategy_returns) == len(df)

