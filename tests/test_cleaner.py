"""Tests for DataCleaner, gap filling, anomaly detection, and quality scoring."""

from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest
from data.cleaner import DataCleaner


def create_sample_ohlcv(
    periods: int = 50,
    interval_minutes: int = 60,
    base_price: float = 50000.0,
    start_time: datetime = None,
) -> pd.DataFrame:
    """Helper to generate synthetic, healthy OHLCV data."""
    if start_time is None:
        start_time = datetime.now(timezone.utc) - timedelta(minutes=periods * interval_minutes)

    timestamps = [start_time + timedelta(minutes=i * interval_minutes) for i in range(periods)]
    data = []
    price = base_price

    for ts in timestamps:
        o = price
        h = price * 1.005
        l = price * 0.995
        c = price * 1.002
        v = 100.0
        data.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})
        price = c

    return pd.DataFrame(data)


def test_quality_score_perfect_data():
    cleaner = DataCleaner()
    df = create_sample_ohlcv(periods=50, interval_minutes=60)
    cleaned, metrics = cleaner.clean_ohlcv(df, timeframe="1h")

    assert len(cleaned) == 50
    assert metrics["gap_count"] == 0
    assert len(metrics["anomalies"]) == 0
    assert metrics["ohlc_violations"] == 0
    assert metrics["quality_score"] >= 0.85


def test_fills_gaps_with_forward_fill():
    cleaner = DataCleaner()
    df = create_sample_ohlcv(periods=30, interval_minutes=60)

    # Intentionally drop candles 10, 11, 12 to create a 3-hour gap
    gap_df = pd.concat([df.iloc[:10], df.iloc[13:]]).reset_index(drop=True)
    assert len(gap_df) == 27

    cleaned, metrics = cleaner.clean_ohlcv(gap_df, timeframe="1h")
    # Cleaned must have the full 30 candles restored
    assert len(cleaned) == 30
    assert metrics["gap_count"] == 3

    # Check forward-filled values
    filled_candle = cleaned.iloc[10]
    prev_close = df.iloc[9]["close"]
    assert filled_candle["open"] == prev_close
    assert filled_candle["close"] == prev_close
    assert filled_candle["volume"] == 0.0


def test_detects_flash_crash():
    cleaner = DataCleaner()
    df = create_sample_ohlcv(periods=30, interval_minutes=60)

    # Inject single candle crash: -10% drop (threshold is 8%)
    df.loc[15, "open"] = 50000.0
    df.loc[15, "high"] = 50000.0
    df.loc[15, "close"] = 45000.0  # -10% body
    df.loc[15, "low"] = 44900.0

    cleaned, metrics = cleaner.clean_ohlcv(df, timeframe="1h")
    body_anomalies = [a for a in metrics["anomalies"] if a["type"] == "BODY_ANOMALY"]
    assert len(body_anomalies) >= 1
    assert body_anomalies[0]["value"] >= 0.08


def test_detects_extreme_wick_anomaly():
    cleaner = DataCleaner()
    df = create_sample_ohlcv(periods=30, interval_minutes=60)

    # Inject huge upper wick: 15% above open (threshold is 12%)
    df.loc[10, "open"] = 50000.0
    df.loc[10, "close"] = 50200.0
    df.loc[10, "high"] = 58000.0  # +16% wick
    df.loc[10, "low"] = 49900.0

    cleaned, metrics = cleaner.clean_ohlcv(df, timeframe="1h")
    wick_anomalies = [a for a in metrics["anomalies"] if a["type"] == "UPPER_WICK_ANOMALY"]
    assert len(wick_anomalies) >= 1
    assert wick_anomalies[0]["value"] >= 0.12


def test_ohlc_violations_detection():
    cleaner = DataCleaner()
    df = create_sample_ohlcv(periods=30, interval_minutes=60)

    # Invert high and low on candle 5 (corrupt data)
    df.loc[5, "high"] = 40000.0
    df.loc[5, "low"] = 60000.0

    cleaned, metrics = cleaner.clean_ohlcv(df, timeframe="1h")
    assert metrics["ohlc_violations"] == 1
    # Should penalize score heavily
    assert metrics["quality_score"] < 0.90


def test_quality_score_bad_data():
    cleaner = DataCleaner()
    df = create_sample_ohlcv(periods=30, interval_minutes=60)

    # Inject multiple defects
    # 1. Drop 5 candles
    df = pd.concat([df.iloc[:5], df.iloc[10:]]).reset_index(drop=True)
    # 2. Corrupt candle
    df.loc[3, "high"] = 10.0
    df.loc[3, "low"] = 99999.0
    # 3. Flash crash
    df.loc[8, "close"] = df.loc[8, "open"] * 0.85

    cleaned, metrics = cleaner.clean_ohlcv(df, timeframe="1h")
    # Low quality data must drop below the 0.70 threshold
    assert metrics["quality_score"] < 0.70
