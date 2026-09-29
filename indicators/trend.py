"""Trend indicators: Exponential Moving Averages, Ribbon Stack, Slope, and SuperTrend."""

from typing import Dict, Tuple
import numpy as np
import pandas as pd


def calculate_ema(series: pd.Series, span: int) -> pd.Series:
    """Calculates Exponential Moving Average with specified span."""
    return series.ewm(span=span, adjust=False).mean()


def calculate_ema_ribbon(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """
    Computes institutional EMA Ribbon: EMA(20), EMA(50), EMA(200).
    """
    close = df["close"]
    return {
        "ema_20": calculate_ema(close, 20),
        "ema_50": calculate_ema(close, 50),
        "ema_200": calculate_ema(close, 200),
    }


def calculate_ema_slope(ema_series: pd.Series, window: int = 5) -> float:
    """
    Calculates normalized percentage slope of an EMA series over a lookback window.
    Positive = Upward velocity, Negative = Downward velocity.
    """
    if len(ema_series) < window or ema_series.iloc[-1] == 0:
        return 0.0

    delta = ema_series.iloc[-1] - ema_series.iloc[-window]
    norm_slope = (delta / ema_series.iloc[-1]) / window
    # Scaled such that 0.1% per candle = +1.0
    return float(np.clip(norm_slope * 1000.0, -1.0, 1.0))


def calculate_supertrend(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    """
    Calculates SuperTrend indicator.
    Returns DataFrame with columns:
    - 'supertrend': Price level of trailing stop
    - 'direction': 1.0 for Bullish (Price > SuperTrend), -1.0 for Bearish
    """
    if len(df) < period + 1:
        return pd.DataFrame({"supertrend": df["close"], "direction": 0.0}, index=df.index)

    hl2 = (df["high"] + df["low"]) / 2.0
    # True range
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()

    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    c = df["close"].values
    bu = basic_upper.values
    bl = basic_lower.values
    fu = bu.copy()
    fl = bl.copy()
    supertrend = np.zeros(len(df))
    direction = np.zeros(len(df))

    for i in range(1, len(df)):
        # Upper band adjustment
        if bu[i] < fu[i - 1] or c[i - 1] > fu[i - 1]:
            fu[i] = bu[i]
        else:
            fu[i] = fu[i - 1]

        # Lower band adjustment
        if bl[i] > fl[i - 1] or c[i - 1] < fl[i - 1]:
            fl[i] = bl[i]
        else:
            fl[i] = fl[i - 1]

        # Direction calculation
        if i == 1:
            direction[i] = 1.0 if c[i] > fu[i] else -1.0
        else:
            if direction[i - 1] == 1.0:
                direction[i] = -1.0 if c[i] < fl[i] else 1.0
            else:
                direction[i] = 1.0 if c[i] > fu[i] else -1.0

        supertrend[i] = fl[i] if direction[i] == 1.0 else fu[i]

    return pd.DataFrame(
        {"supertrend": supertrend, "direction": direction},
        index=df.index
    )
