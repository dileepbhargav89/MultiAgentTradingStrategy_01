"""Unit tests for WalkForwardValidator and Deflated Sharpe Ratio calculation."""

import numpy as np
import pandas as pd
import pytest

from core.types import StrategyGenome, StrategySpecies
from models.walk_forward import WalkForwardValidator


def generate_market_data(periods: int = 400) -> pd.DataFrame:
    np.random.seed(42)
    closes = [50000.0]
    for _ in range(periods - 1):
        closes.append(closes[-1] * (1.0 + np.random.normal(0.0004, 0.005)))

    closes = np.array(closes)
    return pd.DataFrame({
        "open": closes * 0.999,
        "high": closes * 1.003,
        "low": closes * 0.997,
        "close": closes,
        "volume": [1200.0] * periods,
    })


def test_walk_forward_partition_and_embargo():
    df = generate_market_data(periods=200)
    validator = WalkForwardValidator(in_sample_ratio=0.70, embargo_candles=20)
    df_is, df_oos = validator.partition_data(df)

    assert len(df_is) == 140
    # OOS must start at 140 + 20 = 160
    assert len(df_oos) == 40


def test_deflated_sharpe_ratio():
    validator = WalkForwardValidator()
    # Synthetic normal returns with positive Sharpe
    returns = np.random.normal(0.0005, 0.005, 500)
    dsr_high = validator.calculate_deflated_sharpe(oos_sharpe=2.5, oos_returns=returns, trials=100)
    assert 0.0 <= dsr_high <= 1.0

    # Low Sharpe should have very low DSR
    dsr_low = validator.calculate_deflated_sharpe(oos_sharpe=0.2, oos_returns=returns, trials=1000)
    assert dsr_low < dsr_high


def test_walk_forward_validation_audit():
    df = generate_market_data(periods=300)
    genome = StrategyGenome(
        strategy_id="TEST-WF-GENOME",
        species=StrategySpecies.MOMENTUM_TREND,
        trend_filter_lookback=25,
    )

    validator = WalkForwardValidator()
    report = validator.validate(df, genome)

    assert report.strategy_id == genome.strategy_id
    assert isinstance(report.is_overfit, bool)
    assert report.walk_forward_efficiency is not None
    assert 0.0 <= report.deflated_sharpe_ratio <= 1.0


def test_dsr_uses_strategy_returns(monkeypatch):
    df = generate_market_data(periods=300)
    genome = StrategyGenome(
        strategy_id="TEST-WF-RETURNS",
        species=StrategySpecies.MOMENTUM_TREND,
        trend_filter_lookback=25,
    )
    validator = WalkForwardValidator()

    captured = {}
    orig_dsr = validator.calculate_deflated_sharpe

    def mock_dsr(oos_sharpe, oos_returns, trials):
        captured["oos_returns"] = oos_returns
        return orig_dsr(oos_sharpe, oos_returns, trials)

    monkeypatch.setattr(validator, "calculate_deflated_sharpe", mock_dsr)
    validator.validate(df, genome)

    assert captured["oos_returns"] is not None
    assert len(captured["oos_returns"]) == len(validator.partition_data(df)[1])


def test_dsr_fallback_on_missing_returns(monkeypatch):
    df = generate_market_data(periods=300)
    genome = StrategyGenome(
        strategy_id="TEST-WF-FALLBACK",
        species=StrategySpecies.MOMENTUM_TREND,
    )
    validator = WalkForwardValidator()

    orig_backtest = validator.backtester.backtest

    def mock_backtest(d, g):
        res = orig_backtest(d, g)
        res.strategy_returns = None
        return res

    captured = {}

    def mock_dsr(oos_sharpe, oos_returns, trials):
        captured["oos_returns"] = oos_returns
        return 0.5

    monkeypatch.setattr(validator.backtester, "backtest", mock_backtest)
    monkeypatch.setattr(validator, "calculate_deflated_sharpe", mock_dsr)
    validator.validate(df, genome)

    assert len(captured["oos_returns"]) == len(validator.partition_data(df)[1]) - 1

