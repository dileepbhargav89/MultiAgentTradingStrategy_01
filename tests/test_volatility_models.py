"""Unit tests for statistical volatility estimators (Parkinson, Garman-Klass, EWMA, GARCH)."""

import numpy as np
import pandas as pd
import pytest

from models.volatility_models import (
    calculate_ewma_volatility,
    calculate_garman_klass_volatility,
    calculate_parkinson_volatility,
    forecast_garch_volatility,
)


def generate_synthetic_series(periods: int = 50, vol_scale: float = 0.01) -> pd.DataFrame:
    np.random.seed(42)
    returns = np.random.normal(0, vol_scale, periods)
    closes = 50000.0 * np.exp(np.cumsum(returns))

    highs = closes * (1.0 + np.abs(np.random.normal(0, vol_scale, periods)))
    lows = closes * (1.0 - np.abs(np.random.normal(0, vol_scale, periods)))
    opens = closes * (1.0 + np.random.normal(0, vol_scale * 0.5, periods))

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [100.0] * periods,
    })


def test_parkinson_volatility_positive():
    df = generate_synthetic_series(periods=50, vol_scale=0.01)
    p_vol = calculate_parkinson_volatility(df, window=24, timeframe="1h")

    # Annualized volatility for 1% hourly returns should be around 50-150%
    assert p_vol > 0.0
    assert 20.0 <= p_vol <= 250.0


def test_garman_klass_efficiency():
    df = generate_synthetic_series(periods=50, vol_scale=0.01)
    gk_vol = calculate_garman_klass_volatility(df, window=24, timeframe="1h")

    assert gk_vol > 0.0
    assert 20.0 <= gk_vol <= 250.0


def test_ewma_riskmetrics_variance():
    df = generate_synthetic_series(periods=50, vol_scale=0.01)
    log_returns = np.log(df["close"] / df["close"].shift(1)).fillna(0.0)

    ewma_vol = calculate_ewma_volatility(log_returns, lambda_param=0.94, timeframe="1h")
    assert ewma_vol > 0.0


def test_forecast_garch_volatility():
    df = generate_synthetic_series(periods=60, vol_scale=0.015)
    log_returns = np.log(df["close"] / df["close"].shift(1)).fillna(0.0)

    forecast_vol = forecast_garch_volatility(log_returns, horizon_steps=24, timeframe="1h")
    assert forecast_vol > 0.0
    # Forecast should be finite and bounded reasonably
    assert 10.0 <= forecast_vol <= 300.0


def test_garch_fitted_params_non_default():
    from models.volatility_models import _fit_garch_params
    np.random.seed(42)
    r = np.random.normal(0, 0.02, 100)
    alpha, beta = _fit_garch_params(r)
    assert 0.0 < alpha < 1.0
    assert 0.0 < beta < 1.0
    assert alpha + beta < 1.0


def test_garch_fallback_on_short_data():
    from models.volatility_models import _fit_garch_params
    r = np.array([0.01, -0.02, 0.005])
    alpha, beta = _fit_garch_params(r)
    assert (alpha, beta) == (0.08, 0.89)

