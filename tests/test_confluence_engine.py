"""Unit tests for Multi-Timeframe Confluence Engine."""

from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest
from agents.confluence_engine import ConfluenceEngine
from core.types import MarketBias


def generate_market(periods: int = 100, trend: float = 0.0) -> dict[str, pd.DataFrame]:
    now = datetime.now(timezone.utc)
    tf_minutes = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    dataset = {}

    for tf, mins in tf_minutes.items():
        records = []
        base_time = now - timedelta(minutes=periods * mins)
        price = 50000.0
        for i in range(periods):
            ts = base_time + timedelta(minutes=i * mins)
            o = price
            c = price * (1.0 + trend)
            h = max(o, c) * 1.002
            l = min(o, c) * 0.998
            v = 500.0 + (i % 5) * 50.0
            records.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})
            price = c
        dataset[tf] = pd.DataFrame(records)

    return dataset


def test_confluence_perfect_bullish():
    engine = ConfluenceEngine()
    # Strong uptrend across all timeframes
    data = generate_market(periods=210, trend=0.002)

    score, bias, tf_scores, dim_scores = engine.calculate_confluence(data)

    assert score >= 0.50
    assert bias in (MarketBias.BULLISH, MarketBias.STRONG_BULLISH)
    assert tf_scores["1h"] > 0.3
    assert tf_scores["4h"] > 0.3


def test_confluence_perfect_bearish():
    engine = ConfluenceEngine()
    # Strong downtrend across all timeframes
    data = generate_market(periods=210, trend=-0.002)

    score, bias, tf_scores, dim_scores = engine.calculate_confluence(data)

    assert score <= -0.50
    assert bias in (MarketBias.BEARISH, MarketBias.STRONG_BEARISH)
    assert tf_scores["1h"] < -0.3
    assert tf_scores["4h"] < -0.3


def test_counter_trend_damping():
    engine = ConfluenceEngine()
    # 4H in strong downtrend
    data_bear = generate_market(periods=210, trend=-0.003)
    # But 15m in sharp short-term bounce
    data_bull = generate_market(periods=210, trend=0.004)
    data = {
        "15m": data_bull["15m"],
        "1h": data_bear["1h"],
        "4h": data_bear["4h"],
        "1d": data_bear["1d"],
    }

    score, bias, tf_scores, dim_scores = engine.calculate_confluence(data)

    # Because 4H is bear trend, 15m should have been dampened, and overall bias remains bearish or neutral
    assert score < 0.20
    assert bias != MarketBias.STRONG_BULLISH


def test_1h_damped_when_opposing_4h():
    engine = ConfluenceEngine()
    data_bear = generate_market(periods=210, trend=-0.003)
    data_bull = generate_market(periods=210, trend=0.004)
    data = {
        "15m": data_bear["15m"],
        "1h": data_bull["1h"],
        "4h": data_bear["4h"],
        "1d": data_bear["1d"],
    }
    score, bias, tf_scores, dim_scores = engine.calculate_confluence(data)
    # 4H is bear (-), 1H is bull (+), so 1H score was damped by 40% (x 0.60)
    raw_1h, _ = engine.calculate_timeframe_score(data_bull["1h"])
    assert tf_scores["1h"] == pytest.approx(raw_1h * 0.60, rel=1e-2)


def test_correlation_penalty_when_trend_momentum_agree(monkeypatch):
    engine = ConfluenceEngine()
    # Stub calculate_timeframe_score to return high trend and high momentum
    def mock_tf_score(df):
        return 0.80, {"trend": 0.80, "momentum": 0.80, "volatility": 0.50, "volume": 0.50}

    monkeypatch.setattr(engine, "calculate_timeframe_score", mock_tf_score)
    data = generate_market(periods=50)
    score, _, _, dims = engine.calculate_confluence(data)
    # Weighted average is 0.80. With 0.08 penalty, score should be 0.72
    assert score == pytest.approx(0.72, rel=1e-3)

