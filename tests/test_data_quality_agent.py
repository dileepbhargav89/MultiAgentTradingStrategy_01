"""Tests for DataQualityAgent decision-making, state transitions, and veto power."""

from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest
from agents.data_quality_agent import DataQualityAgent
from core.events import EVENT_DATA_QUALITY_HALT, EVENT_DATA_QUALITY_REPORT, event_bus
from core.types import AgentState


def generate_timeframe_dataset(periods: int = 50, now: datetime = None) -> dict[str, pd.DataFrame]:
    if now is None:
        now = datetime.now(timezone.utc)

    dataset = {}
    timeframe_minutes = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}

    for tf, minutes in timeframe_minutes.items():
        records = []
        base_time = now - timedelta(minutes=periods * minutes)
        price = 50000.0
        for i in range(periods):
            ts = base_time + timedelta(minutes=i * minutes)
            records.append({
                "timestamp": ts,
                "open": price,
                "high": price * 1.002,
                "low": price * 0.998,
                "close": price * 1.001,
                "volume": 200.0,
            })
            price = price * 1.001
        dataset[tf] = pd.DataFrame(records)

    return dataset


def test_agent_healthy_on_good_data():
    agent = DataQualityAgent()
    data = generate_timeframe_dataset(periods=60)
    report = agent.evaluate_data("BTC/USDT", data)

    assert report.status == AgentState.HEALTHY
    assert report.is_tradeable is True
    assert report.overall_quality >= 0.85
    assert len(report.warnings) == 0


def test_agent_halts_on_low_quality():
    agent = DataQualityAgent()
    data = generate_timeframe_dataset(periods=60)

    # Intentionally corrupt 15m and 1h with lots of missing candles and invalid OHLC
    data["15m"] = pd.concat([data["15m"].iloc[:10], data["15m"].iloc[30:]]).reset_index(drop=True)
    data["1h"].loc[5:15, "high"] = 1.0
    data["1h"].loc[5:15, "low"] = 99999.0

    halt_events = []
    event_bus.subscribe(EVENT_DATA_QUALITY_HALT, lambda d: halt_events.append(d))

    report = agent.evaluate_data("BTC/USDT", data)

    assert report.status == AgentState.HALTED
    assert report.is_tradeable is False
    assert len(halt_events) >= 1
    assert halt_events[-1]["symbol"] == "BTC/USDT"


def test_agent_degraded_on_stale_data():
    agent = DataQualityAgent()
    # Stale dataset from 10 hours ago
    stale_time = datetime.now(timezone.utc) - timedelta(hours=10)
    data = generate_timeframe_dataset(periods=50, now=stale_time)

    report = agent.evaluate_data("BTC/USDT", data)

    # Should flag stale data
    assert report.freshness_ok is False
    assert report.status in (AgentState.DEGRADED, AgentState.HALTED)


def test_cross_timeframe_discrepancy_triggers_halt():
    agent = DataQualityAgent()
    data = generate_timeframe_dataset(periods=50)

    # Synchronize an exact timestamp between 1h and 4h with contradictory prices
    common_ts = data["4h"]["timestamp"].iloc[-1]
    data["1h"].loc[data["1h"].index[-1], "timestamp"] = common_ts
    data["1h"].loc[data["1h"].index[-1], "close"] = 50000.0
    data["4h"].loc[data["4h"].index[-1], "close"] = 55000.0  # 10% discrepancy!

    report = agent.evaluate_data("BTC/USDT", data)

    assert report.status == AgentState.HALTED
    assert report.is_tradeable is False
    assert any("Cross-timeframe" in w for w in report.warnings)


def test_build_data_packet():
    agent = DataQualityAgent()
    data = generate_timeframe_dataset(periods=50)
    report = agent.evaluate_data("BTC/USDT", data, spread_pct=0.0002, live_price=52000.0)

    packet = agent.build_data_packet("BTC/USDT")
    assert packet is not None
    assert packet.symbol == "BTC/USDT"
    assert "15m" in packet.timeframes
    assert "15m" in packet.features
    assert packet.quality.status == AgentState.HEALTHY
    assert packet.latest_price == 52000.0
    assert packet.spread_pct == 0.0002


def test_data_quality_elevated_spread():
    agent = DataQualityAgent()
    data = generate_timeframe_dataset(periods=50)
    # 2% spread blowout
    report = agent.evaluate_data("BTC/USDT", data, spread_pct=0.02)
    assert any("spread blowout" in w.lower() for w in report.warnings)


def test_all_stale_triggers_halt():
    agent = DataQualityAgent()
    stale_time = datetime.now(timezone.utc) - timedelta(hours=10)
    data = generate_timeframe_dataset(periods=50, now=stale_time)

    report = agent.evaluate_data("BTC/USDT", data)
    assert report.status == AgentState.HALTED
    assert report.is_tradeable is False
    assert any("ALL timeframes stale" in w for w in report.warnings)


def test_partial_stale_remains_degraded():
    agent = DataQualityAgent()
    now = datetime.now(timezone.utc)
    data = generate_timeframe_dataset(periods=50, now=now)

    # Make only 4h and 1d stale
    stale_4h = generate_timeframe_dataset(periods=50, now=now - timedelta(hours=50))
    data["4h"] = stale_4h["4h"]
    data["1d"] = stale_4h["1d"]

    report = agent.evaluate_data("BTC/USDT", data)
    assert report.status == AgentState.DEGRADED
    assert report.is_tradeable is True
    assert report.freshness_ok is False

