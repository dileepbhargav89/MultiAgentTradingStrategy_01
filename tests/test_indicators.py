"""Unit tests for technical indicators and orthogonal normalizer."""

from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import pytest

from indicators.momentum import calculate_macd, calculate_macd_acceleration, calculate_rsi
from indicators.normalizer import SignalNormalizer
from indicators.trend import (
    calculate_ema,
    calculate_ema_ribbon,
    calculate_ema_slope,
    calculate_supertrend,
)
from indicators.volatility import calculate_atr, calculate_bollinger_bands, calculate_natr
from indicators.volume import calculate_volume_divergence, calculate_vwap, calculate_vwma


def generate_synthetic_candles(periods: int = 100, trend: float = 0.001) -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    records = []
    price = 50000.0

    for i in range(periods):
        ts = now - timedelta(hours=periods - i)
        o = price
        c = price * (1.0 + trend)
        h = max(o, c) * 1.003
        l = min(o, c) * 0.997
        v = 100.0 + (i % 10) * 10.0
        records.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})
        price = c

    return pd.DataFrame(records)


def test_ema_ribbon_and_slope():
    df = generate_synthetic_candles(periods=220, trend=0.002)  # Steady uptrend
    ribbon = calculate_ema_ribbon(df)

    assert "ema_20" in ribbon
    assert "ema_50" in ribbon
    assert "ema_200" in ribbon

    # In a steady uptrend: Price > EMA20 > EMA50 > EMA200
    close = df["close"].iloc[-1]
    e20 = ribbon["ema_20"].iloc[-1]
    e50 = ribbon["ema_50"].iloc[-1]
    e200 = ribbon["ema_200"].iloc[-1]

    assert close > e20 > e50 > e200

    slope = calculate_ema_slope(ribbon["ema_50"], window=5)
    assert slope > 0.0


def test_supertrend_calculation():
    df = generate_synthetic_candles(periods=50, trend=0.003)
    st_df = calculate_supertrend(df, period=10, multiplier=3.0)

    assert "supertrend" in st_df.columns
    assert "direction" in st_df.columns
    # In uptrend, direction should be 1.0
    assert st_df["direction"].iloc[-1] == 1.0
    assert df["close"].iloc[-1] > st_df["supertrend"].iloc[-1]


def test_rsi_wilder_smoothing():
    df_up = generate_synthetic_candles(periods=50, trend=0.005)
    rsi_up = calculate_rsi(df_up["close"], 14)
    # Strong uptrend RSI should be > 65
    assert rsi_up.iloc[-1] > 65.0

    df_down = generate_synthetic_candles(periods=50, trend=-0.005)
    rsi_down = calculate_rsi(df_down["close"], 14)
    # Strong downtrend RSI should be < 35
    assert rsi_down.iloc[-1] < 35.0


def test_macd_and_acceleration():
    df = generate_synthetic_candles(periods=60, trend=0.002)
    macd_res = calculate_macd(df["close"], 12, 26, 9)

    assert "macd" in macd_res
    assert "signal" in macd_res
    assert "histogram" in macd_res
    assert macd_res["histogram"].iloc[-1] > 0.0

    accel = calculate_macd_acceleration(macd_res["histogram"], window=3)
    assert -1.0 <= accel <= 1.0


def test_bollinger_bands_and_atr():
    df = generate_synthetic_candles(periods=50)
    bb = calculate_bollinger_bands(df["close"], 20, 2.0)

    assert bb["upper"].iloc[-1] > bb["middle"].iloc[-1] > bb["lower"].iloc[-1]
    assert 0.0 <= bb["percent_b"].iloc[-1] <= 1.0
    assert bb["bandwidth"].iloc[-1] > 0.0

    atr = calculate_atr(df, 14)
    natr = calculate_natr(df, 14)
    assert atr.iloc[-1] > 0.0
    assert natr.iloc[-1] > 0.0


def test_vwap_and_vwma():
    df = generate_synthetic_candles(periods=50)
    vwap = calculate_vwap(df)
    vwma = calculate_vwma(df, 20)

    assert len(vwap) == len(df)
    assert len(vwma) == len(df)
    assert vwap.iloc[-1] > 0.0
    assert vwma.iloc[-1] > 0.0

    divergence = calculate_volume_divergence(df, 20)
    assert -1.0 <= divergence <= 1.0


def test_signal_normalizer_bounds():
    df = generate_synthetic_candles(periods=210, trend=0.002)
    dims = SignalNormalizer.normalize_all(df)

    for dim_name, score in dims.items():
        assert -1.0 <= score <= 1.0, f"Dimension {dim_name} out of bounds: {score}"

    # In a strong uptrend, trend and momentum should be positive
    assert dims["trend"] > 0.3
    assert dims["momentum"] > 0.2


def test_session_vwap_resets_at_boundary():
    from indicators.volume import calculate_session_vwap
    now = datetime(2026, 3, 15, 0, 0, 0, tzinfo=timezone.utc)
    records = []
    # Day 1: 12 candles with price 50000, volume 100
    for i in range(12):
        records.append({
            "timestamp": now + timedelta(hours=i),
            "open": 50000.0, "high": 50100.0, "low": 49900.0, "close": 50000.0, "volume": 100.0
        })
    # Day 2: 12 candles with price 60000, volume 100
    day2 = now + timedelta(days=1)
    for i in range(12):
        records.append({
            "timestamp": day2 + timedelta(hours=i),
            "open": 60000.0, "high": 60100.0, "low": 59900.0, "close": 60000.0, "volume": 100.0
        })
    df = pd.DataFrame(records)
    session_vwap = calculate_session_vwap(df, session_hours=24)

    # First candle of Day 2 should equal Day 2's typical price (60000), not blended with Day 1
    assert session_vwap.iloc[12] == pytest.approx(60000.0, rel=1e-3)


def test_bb_extreme_overextension_negative():
    closes = [50000.0] * 20 + [65000.0]
    df = pd.DataFrame({
        "open": closes, "high": closes, "low": closes, "close": closes, "volume": [100.0] * len(closes)
    })
    score = SignalNormalizer.normalize_volatility(df)
    assert score < 0.0, f"Expected negative mean-reversion score on extreme pump, got {score}"


def test_bb_extreme_oversold_positive():
    closes = [50000.0] * 20 + [35000.0]
    df = pd.DataFrame({
        "open": closes, "high": closes, "low": closes, "close": closes, "volume": [100.0] * len(closes)
    })
    score = SignalNormalizer.normalize_volatility(df)
    assert score > 0.0, f"Expected positive bounce score on extreme dump, got {score}"

