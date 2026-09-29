"""Unit tests for RegimeClassifier and VolatilityMultiplierCalculator."""

import numpy as np
import pandas as pd
import pytest

from core.types import VolatilityRegime
from models.regime_classifier import RegimeClassifier
from models.volatility_multiplier import VolatilityMultiplierCalculator


def generate_flat_series(periods: int = 100) -> pd.DataFrame:
    """Simulates ultra-low volatility compression range."""
    closes = [50000.0 + (i % 3) * 5.0 for i in range(periods)]
    return pd.DataFrame({
        "open": closes,
        "high": [c + 10.0 for c in closes],
        "low": [c - 10.0 for c in closes],
        "close": closes,
        "volume": [100.0] * periods,
    })


def generate_wild_series(periods: int = 100) -> pd.DataFrame:
    """Simulates extreme high-volatility chaos."""
    np.random.seed(99)
    changes = np.random.normal(0, 0.05, periods)  # 5% hourly swings!
    closes = 50000.0 * np.exp(np.cumsum(changes))
    return pd.DataFrame({
        "open": closes,
        "high": closes * 1.06,
        "low": closes * 0.94,
        "close": closes,
        "volume": [1000.0] * periods,
    })


def test_low_vol_compression_detection():
    df_flat = generate_flat_series(periods=100)
    regime, percentile, is_breakout = RegimeClassifier.classify_regime(
        df=df_flat,
        current_parkinson_vol=5.0,  # Extremely low 5% vol
    )

    assert regime == VolatilityRegime.LOW_VOL_COMPRESSION
    assert is_breakout is True


def test_high_vol_chaos_detection():
    df_normal = generate_flat_series(periods=80)
    df_wild = generate_wild_series(periods=20)
    df = pd.concat([df_normal, df_wild], ignore_index=True)
    cur_vol = 500.0  # Extreme volatility surge above baseline

    regime, percentile, is_breakout = RegimeClassifier.classify_regime(
        df=df,
        current_parkinson_vol=cur_vol,
    )

    assert regime == VolatilityRegime.HIGH_VOL_CHAOS
    assert percentile >= 75.0


def test_multipliers_scaling():
    # In compression: size multiplier should be neutral/defensive (0.90x), stop tight (1.30x)
    size_c, stop_c = VolatilityMultiplierCalculator.calculate_multipliers(
        regime=VolatilityRegime.LOW_VOL_COMPRESSION,
        volatility_percentile=10.0,
    )
    assert size_c == 0.90
    assert stop_c == 1.30

    # In chaos: size multiplier should be downscaled (<= 0.60x), stop wide (>= 2.0x)
    size_h, stop_h = VolatilityMultiplierCalculator.calculate_multipliers(
        regime=VolatilityRegime.HIGH_VOL_CHAOS,
        volatility_percentile=90.0,
    )
    assert size_h <= 0.60
    assert stop_h >= 2.00


def test_compression_regime_does_not_upscale():
    size, _ = VolatilityMultiplierCalculator.calculate_multipliers(
        regime=VolatilityRegime.LOW_VOL_COMPRESSION,
        volatility_percentile=5.0,
    )
    assert size <= 1.0, f"Expected compression sizing <= 1.0, got {size}"

