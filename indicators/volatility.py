"""Volatility and envelope indicators: Average True Range (ATR), NATR, and Bollinger Bands."""

from typing import Dict
import numpy as np
import pandas as pd


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Computes Wilder's Average True Range (ATR).
    """
    if len(df) < 2:
        return pd.Series(0.0, index=df.index)

    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr.fillna(tr)


def calculate_natr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Computes Normalized Average True Range (NATR) as a percentage of close price.
    """
    atr = calculate_atr(df, period)
    close = df["close"].replace(0.0, np.nan)
    natr = (atr / close) * 100.0
    return natr.fillna(0.0)


def calculate_bollinger_bands(
    series: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> Dict[str, pd.Series]:
    """
    Computes Bollinger Bands, Percent B (%B), and Bandwidth.
    Returns dict: 'upper', 'middle', 'lower', 'percent_b', 'bandwidth'.
    """
    middle = series.rolling(window=period, min_periods=1).mean()
    std = series.rolling(window=period, min_periods=1).std().fillna(0.0)

    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)

    band_range = (upper - lower).replace(0.0, np.nan)
    percent_b = (series - lower) / band_range
    percent_b = percent_b.fillna(0.5)

    bandwidth = ((upper - lower) / middle.replace(0.0, np.nan)).fillna(0.0)

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "percent_b": percent_b,
        "bandwidth": bandwidth,
    }
