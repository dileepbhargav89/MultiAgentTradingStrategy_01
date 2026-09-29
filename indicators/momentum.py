"""Momentum indicators: Wilder's RSI, MACD with signal line, and histogram acceleration."""

from typing import Dict
import numpy as np
import pandas as pd


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Computes Relative Strength Index using Wilder's original exponential smoothing.
    """
    if len(series) < period:
        return pd.Series(50.0, index=series.index)

    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    # Wilder's smoothing corresponds to alpha = 1 / period
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # Handle edge case where loss is zero (RSI = 100) or gain is zero (RSI = 0)
    rsi = rsi.fillna(100.0).clip(0.0, 100.0)
    return rsi


def calculate_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Dict[str, pd.Series]:
    """
    Computes standard Moving Average Convergence Divergence (MACD).
    Returns dict with keys: 'macd', 'signal', 'histogram'.
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram,
    }


def calculate_macd_acceleration(hist_series: pd.Series, window: int = 3) -> float:
    """
    Measures rate of change (acceleration) in MACD histogram over window periods.
    Positive = Momentum accelerating upward, Negative = Decelerating.
    """
    if len(hist_series) < window + 1:
        return 0.0

    delta = hist_series.iloc[-1] - hist_series.iloc[-window]
    hist_range = float(hist_series.tail(window * 3).abs().max()) if len(hist_series) > window * 3 else 1.0
    ref = abs(hist_series.iloc[-window]) + max(1e-6, hist_range * 0.00001)
    accel = delta / ref
    return float(np.clip(accel, -1.0, 1.0))
