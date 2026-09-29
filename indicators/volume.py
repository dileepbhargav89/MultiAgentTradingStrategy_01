"""Volume-weighted indicators: VWAP, VWMA, and Volume Divergence."""

import numpy as np
import pandas as pd


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Computes Cumulative Volume-Weighted Average Price (VWAP) across candle series.
    Typical Price = (High + Low + Close) / 3
    """
    if len(df) == 0:
        return pd.Series(dtype=float)

    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_vol_price = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum().replace(0.0, np.nan)

    vwap = cum_vol_price / cum_vol
    return vwap.fillna(typical_price)


def calculate_session_vwap(df: pd.DataFrame, session_hours: int = 24) -> pd.Series:
    """Computes session-anchored VWAP that resets every `session_hours` hours."""
    if len(df) == 0:
        return pd.Series(dtype=float)

    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0

    # Determine session boundaries (reset at UTC midnight by default)
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"])
        session_ids = ts.dt.floor(f"{session_hours}h")
    else:
        # Fallback: reset every session_hours candles
        session_ids = pd.Series(range(len(df)), index=df.index) // session_hours

    cum_vol_price = (typical_price * df["volume"]).groupby(session_ids).cumsum()
    cum_vol = df["volume"].groupby(session_ids).cumsum().replace(0.0, np.nan)

    vwap = cum_vol_price / cum_vol
    return vwap.fillna(typical_price)



def calculate_vwma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    Computes rolling Volume-Weighted Moving Average (VWMA).
    """
    if len(df) < period:
        return df["close"].copy()

    vol_price = df["close"] * df["volume"]
    roll_vol_price = vol_price.rolling(window=period, min_periods=1).sum()
    roll_vol = df["volume"].rolling(window=period, min_periods=1).sum().replace(0.0, np.nan)

    vwma = roll_vol_price / roll_vol
    return vwma.fillna(df["close"])


def calculate_volume_divergence(df: pd.DataFrame, period: int = 20) -> float:
    """
    Measures percentage divergence between VWMA and standard SMA:
    (VWMA - SMA) / SMA
    Positive = Volume concentrated at higher prices (Institutional Accumulation)
    Negative = Volume concentrated at lower prices (Institutional Distribution)
    """
    if len(df) < period:
        return 0.0

    vwma = calculate_vwma(df, period).iloc[-1]
    sma = df["close"].rolling(window=period, min_periods=1).mean().iloc[-1]

    if sma == 0.0 or np.isnan(sma):
        return 0.0

    divergence = (vwma - sma) / sma

    # Adaptive scaling: use rolling divergence std to normalize when sufficient history exists
    if len(df) >= period * 2:
        vwma_series = calculate_vwma(df, period)
        sma_series = df["close"].rolling(window=period, min_periods=1).mean()
        div_series = ((vwma_series - sma_series) / sma_series.replace(0.0, np.nan)).dropna()
        div_std = float(div_series.std()) if len(div_series) > 5 else 0.01
        adaptive_scale = 0.5 / max(div_std, 1e-6)  # Maps 1 std → 0.5 score
        return float(np.clip(divergence * adaptive_scale, -1.0, 1.0))
    else:
        return float(np.clip(divergence * 50.0, -1.0, 1.0))

