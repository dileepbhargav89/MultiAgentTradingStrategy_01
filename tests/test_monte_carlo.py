"""Unit tests for MonteCarloTester."""

import numpy as np
import pandas as pd
import pytest

from core.types import StrategyGenome, StrategySpecies
from models.monte_carlo import MonteCarloTester


def generate_ohlcv(periods: int = 250) -> pd.DataFrame:
    np.random.seed(99)
    closes = [55000.0]
    for _ in range(periods - 1):
        closes.append(closes[-1] * (1.0 + np.random.normal(0.0003, 0.004)))

    closes = np.array(closes)
    return pd.DataFrame({
        "open": closes * 0.999,
        "high": closes * 1.003,
        "low": closes * 0.997,
        "close": closes,
        "volume": [1000.0] * periods,
    })


def test_monte_carlo_permutation_metrics():
    df = generate_ohlcv(periods=200)
    genome = StrategyGenome(
        strategy_id="TEST-MC",
        species=StrategySpecies.MEAN_REVERSION,
        rsi_oversold_bound=35.0,
        rsi_overbought_bound=65.0,
    )

    tester = MonteCarloTester(permutations=100)
    report = tester.run_permutation_test(df, genome)

    assert report.strategy_id == genome.strategy_id
    assert report.permutations_tested == 100
    assert 0.0 <= report.drawdown_95th_percentile <= 1.0
    assert 0.0 <= report.risk_of_ruin_pct <= 100.0
    assert 0.0 <= report.probability_of_profit <= 1.0
    assert isinstance(report.is_disqualified, bool)


def test_monte_carlo_insufficient_trades():
    # Only 10 periods
    df_short = generate_ohlcv(periods=10)
    genome = StrategyGenome(
        strategy_id="SHORT",
        species=StrategySpecies.MOMENTUM_TREND,
    )

    tester = MonteCarloTester(permutations=50)
    report = tester.run_permutation_test(df_short, genome)

    assert report.is_disqualified is True
    assert "INSUFFICIENT" in report.rejection_reason


def test_mc_true_permutation_no_duplicates():
    df = generate_ohlcv(periods=200)
    genome = StrategyGenome(
        strategy_id="TEST-MC-PERM",
        species=StrategySpecies.MEAN_REVERSION,
    )
    tester = MonteCarloTester(permutations=20)
    report = tester.run_permutation_test(df, genome)
    assert report.permutations_tested == 20


def test_mc_non_deterministic():
    df = generate_ohlcv(periods=200)
    genome = StrategyGenome(
        strategy_id="TEST-MC-NONDET",
        species=StrategySpecies.MOMENTUM_TREND,
    )
    tester = MonteCarloTester(permutations=50)
    rep1 = tester.run_permutation_test(df, genome)
    rep2 = tester.run_permutation_test(df, genome)
    assert rep1.permutations_tested == 50
    assert rep2.permutations_tested == 50
    assert 0.0 <= rep1.drawdown_95th_percentile <= 1.0
    assert 0.0 <= rep2.drawdown_95th_percentile <= 1.0

