"""Unit tests for SpeciesStrategyBuilder across all 4 species."""

import numpy as np
import pandas as pd
import pytest

from core.types import StrategyGenome, StrategySpecies, VolatilityRegime
from engine.species_strategies import SpeciesStrategyBuilder


def generate_test_ohlcv(periods: int = 150, trend: float = 0.001) -> pd.DataFrame:
    np.random.seed(42)
    closes = [50000.0]
    for _ in range(periods - 1):
        ret = np.random.normal(trend, 0.005)
        closes.append(closes[-1] * (1.0 + ret))

    closes = np.array(closes)
    return pd.DataFrame({
        "open": closes * 0.999,
        "high": closes * 1.004,
        "low": closes * 0.996,
        "close": closes,
        "volume": [1500.0] * periods,
    })


def test_momentum_trend_signals():
    df_uptrend = generate_test_ohlcv(periods=100, trend=0.005)
    genome = StrategyGenome(
        strategy_id="TEST-MOM",
        species=StrategySpecies.MOMENTUM_TREND,
        entry_signal_threshold=0.25,
        trend_filter_lookback=20,
    )

    signals = SpeciesStrategyBuilder.generate_signals(df_uptrend, genome)
    assert len(signals) == len(df_uptrend)
    assert set(np.unique(signals)).issubset({-1.0, 0.0, 1.0})
    # In a strong uptrend, momentum strategy should produce long signals (1.0)
    assert np.sum(signals == 1.0) > 0


def test_mean_reversion_signals():
    # Oscillating series
    periods = 100
    t = np.linspace(0, 10 * np.pi, periods)
    closes = 50000.0 + 2000.0 * np.sin(t)
    df_osc = pd.DataFrame({
        "open": closes,
        "high": closes + 50.0,
        "low": closes - 50.0,
        "close": closes,
        "volume": [1000.0] * periods,
    })

    genome = StrategyGenome(
        strategy_id="TEST-MR",
        species=StrategySpecies.MEAN_REVERSION,
        rsi_oversold_bound=35.0,
        rsi_overbought_bound=65.0,
    )

    signals = SpeciesStrategyBuilder.generate_signals(df_osc, genome)
    assert len(signals) == periods
    # Oscillating series should produce both Long (1.0) and Short (-1.0) signals
    assert np.sum(signals == 1.0) > 0
    assert np.sum(signals == -1.0) > 0


def test_breakout_volatility_signals():
    df = generate_test_ohlcv(periods=100, trend=0.002)
    genome = StrategyGenome(
        strategy_id="TEST-BRK",
        species=StrategySpecies.BREAKOUT_VOLATILITY,
    )

    signals = SpeciesStrategyBuilder.generate_signals(df, genome)
    assert len(signals) == len(df)
    assert set(np.unique(signals)).issubset({-1.0, 0.0, 1.0})


def test_regime_adaptive_signals():
    df = generate_test_ohlcv(periods=100, trend=0.001)
    df["regime"] = [VolatilityRegime.TRENDING_EXPANSION] * 100

    genome = StrategyGenome(
        strategy_id="TEST-ADAPT",
        species=StrategySpecies.REGIME_ADAPTIVE,
    )

    signals = SpeciesStrategyBuilder.generate_signals(df, genome)
    assert len(signals) == len(df)
    assert set(np.unique(signals)).issubset({-1.0, 0.0, 1.0})
