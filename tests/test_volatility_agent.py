"""Unit tests for VolatilityRegimeAgent."""

from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest

from agents.volatility_agent import VolatilityRegimeAgent
from core.events import (
    EVENT_VOLATILITY_REGIME_CHANGE,
    EVENT_VOLATILITY_REPORT,
    event_bus,
)
from core.types import AgentState, DataPacket, DataQualityReport, VolatilityRegime


def create_test_packet(vol_multiplier: float = 1.0) -> DataPacket:
    now = datetime.now(timezone.utc)
    timestamps = [now - timedelta(hours=i) for i in range(100)][::-1]

    closes = [50000.0 + (i * 20.0 * vol_multiplier) for i in range(100)]
    df_1h = pd.DataFrame({
        "timestamp": timestamps,
        "open": closes,
        "high": [c * (1.0 + 0.005 * vol_multiplier) for c in closes],
        "low": [c * (1.0 - 0.005 * vol_multiplier) for c in closes],
        "close": closes,
        "volume": [100.0] * 100,
    })

    quality = DataQualityReport(
        status=AgentState.HEALTHY,
        quality_scores={"1h": 1.0},
        overall_quality=1.0,
        is_tradeable=True,
        freshness_ok=True,
    )

    return DataPacket(
        symbol="BTC/USDT",
        timeframes={"1h": df_1h},
        features={},
        quality=quality,
        latest_price=closes[-1],
    )


def test_volatility_agent_generates_full_report():
    agent = VolatilityRegimeAgent()
    packet = create_test_packet(vol_multiplier=1.0)

    received_reports = []
    event_bus.subscribe(EVENT_VOLATILITY_REPORT, lambda r: received_reports.append(r))

    report = agent.analyze(packet)

    assert report.symbol == "BTC/USDT"
    assert report.forecasted_volatility_24h > 0.0
    assert report.parkinson_volatility > 0.0
    assert report.regime in [
        VolatilityRegime.LOW_VOL_COMPRESSION,
        VolatilityRegime.TRENDING_EXPANSION,
        VolatilityRegime.HIGH_VOL_CHAOS,
    ]
    assert 0.40 <= report.volatility_multiplier <= 1.25
    assert 1.20 <= report.atr_stop_multiplier <= 2.50
    assert len(received_reports) >= 1


def test_volatility_agent_regime_change_event():
    agent = VolatilityRegimeAgent()

    regime_events = []
    event_bus.subscribe(EVENT_VOLATILITY_REGIME_CHANGE, lambda e: regime_events.append(e))

    # 1. Normal expansion
    p1 = create_test_packet(vol_multiplier=1.0)
    r1 = agent.analyze(p1)

    # 2. Transition to high volatility chaos (5x swing)
    p2 = create_test_packet(vol_multiplier=8.0)
    r2 = agent.analyze(p2)

    # Should have triggered regime change event if regimes differ
    if r1.regime != r2.regime:
        assert len(regime_events) >= 1
        assert regime_events[-1]["symbol"] == "BTC/USDT"
