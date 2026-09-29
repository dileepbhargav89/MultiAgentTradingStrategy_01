"""Tests for FeatureEngineer calculations."""

import numpy as np
import pandas as pd
import pytest
from data.features import FeatureEngineer


def test_log_returns_calculation():
    engineer = FeatureEngineer()
    df = pd.DataFrame({
        "open": [100.0, 105.0, 110.0],
        "high": [105.0, 110.0, 115.0],
        "low": [98.0, 102.0, 108.0],
        "close": [100.0, 110.0, 105.0],
        "volume": [1000.0, 1200.0, 800.0],
    })

    features = engineer.compute_features(df, timeframe="1h")

    # Row 0: 0.0
    # Row 1: ln(110/100) = ln(1.1) ~= 0.095310
    # Row 2: ln(105/110) = ln(0.954545) ~= -0.046520
    assert features["log_returns"].iloc[0] == 0.0
    expected_row1 = np.log(110.0 / 100.0)
    assert pytest.approx(features["log_returns"].iloc[1], 1e-5) == expected_row1
    expected_row2 = np.log(105.0 / 110.0)
    assert pytest.approx(features["log_returns"].iloc[2], 1e-5) == expected_row2


def test_rolling_volatility():
    engineer = FeatureEngineer()
    np.random.seed(42)
    closes = 50000.0 * np.exp(np.cumsum(np.random.normal(0, 0.01, 100)))

    df = pd.DataFrame({
        "open": closes,
        "high": closes * 1.01,
        "low": closes * 0.99,
        "close": closes,
        "volume": [100.0] * 100,
    })

    features = engineer.compute_features(df, timeframe="1h")

    # Volatility should be positive and bounded realistically
    vol_24h = features["volatility_24h"].iloc[-1]
    vol_7d = features["volatility_7d"].iloc[-1]

    assert vol_24h > 0.0
    assert vol_7d > 0.0
    # For daily std of ~0.01, rolling std should be close to 0.01
    assert 0.003 < vol_24h < 0.03


def test_range_pct_and_body_wick_ratio():
    engineer = FeatureEngineer()
    df = pd.DataFrame({
        "open": [100.0],
        "high": [110.0],
        "low": [90.0],
        "close": [106.0],
        "volume": [500.0],
    })

    features = engineer.compute_features(df, timeframe="1h")

    # Range pct = (110 - 90) / 106 = 20 / 106 ~= 0.188679
    expected_range = (110.0 - 90.0) / 106.0
    assert pytest.approx(features["range_pct"].iloc[0], 1e-4) == expected_range

    # Body-to-wick = |106 - 100| / (110 - 90) = 6 / 20 = 0.30
    assert pytest.approx(features["body_wick_ratio"].iloc[0], 1e-4) == 0.30


def test_volume_sma_ratio():
    engineer = FeatureEngineer()
    volumes = [100.0] * 19 + [500.0]  # 19 normal candles then 5x surge
    df = pd.DataFrame({
        "open": [100.0] * 20,
        "high": [101.0] * 20,
        "low": [99.0] * 20,
        "close": [100.0] * 20,
        "volume": volumes,
    })

    features = engineer.compute_features(df, timeframe="1h")

    # Average of 19*100 + 500 = 2400 / 20 = 120.
    # Surge ratio = 500 / 120 = 4.1666...
    ratio = features["volume_sma_ratio"].iloc[-1]
    assert ratio > 3.5
