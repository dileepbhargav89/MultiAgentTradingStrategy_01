"""Unit tests for TechnicalAgent decision making, invalidation levels, and event publishing."""

from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest

from agents.data_quality_agent import DataQualityAgent
from agents.technical_agent import TechnicalAgent
from core.events import EVENT_TECHNICAL_REPORT, event_bus
from core.types import AgentState, DataPacket, DataQualityReport, MarketBias


def generate_market(periods: int = 100, trend: float = 0.001) -> dict[str, pd.DataFrame]:
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


def test_technical_agent_respects_data_quality_veto():
    agent = TechnicalAgent()
    data = generate_market(periods=50)

    halted_quality = DataQualityReport(
        status=AgentState.HALTED,
        quality_scores={},
        overall_quality=0.40,
        is_tradeable=False,  # VETO ACTIVE
        freshness_ok=False,
    )

    packet = DataPacket(
        symbol="BTC/USDT",
        timeframes=data,
        features={},
        quality=halted_quality,
        latest_price=50000.0,
    )

    report = agent.analyze(packet)

    assert report.bias == MarketBias.NEUTRAL
    assert report.confluence_score == 0.0
    assert report.symbol == "BTC/USDT"


def test_technical_agent_full_analysis():
    dq_agent = DataQualityAgent()
    tech_agent = TechnicalAgent()
    data = generate_market(periods=100, trend=0.001)

    dq_agent.evaluate_data("BTC/USDT", data)
    packet = dq_agent.build_data_packet("BTC/USDT")
    assert packet is not None
    assert packet.quality.is_tradeable is True

    received_reports = []
    event_bus.subscribe(EVENT_TECHNICAL_REPORT, lambda r: received_reports.append(r))

    report = tech_agent.analyze(packet)

    assert report.symbol == "BTC/USDT"
    assert -1.0 <= report.confluence_score <= 1.0
    assert report.bias in [
        MarketBias.STRONG_BULLISH,
        MarketBias.BULLISH,
        MarketBias.NEUTRAL,
        MarketBias.BEARISH,
        MarketBias.STRONG_BEARISH,
    ]
    # For a bullish trend, invalidation price should be below current price
    assert report.invalidation_price < packet.latest_price
    # Target 1R and 2R should be above current price for longs
    if report.confluence_score > 0:
        assert report.target_1r > packet.latest_price
        assert report.target_2r > report.target_1r

    assert len(received_reports) >= 1
    assert received_reports[-1].symbol == "BTC/USDT"
