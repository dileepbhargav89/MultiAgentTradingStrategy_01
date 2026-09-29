"""Unit tests for MarketIntelligenceAgent decision making and event alerts."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pandas as pd
import pytest

from agents.market_agent import MarketIntelligenceAgent
from core.events import (
    EVENT_MARKET_INTELLIGENCE_ALERT,
    EVENT_MARKET_INTELLIGENCE_REPORT,
    event_bus,
)
from core.types import AgentState, CrowdingBias, DataPacket, DataQualityReport, PositioningQuadrant


def create_dummy_packet() -> DataPacket:
    now = datetime.now(timezone.utc)
    timestamps = [now - timedelta(hours=i) for i in range(30)][::-1]
    df_1h = pd.DataFrame({
        "timestamp": timestamps,
        "open": [50000.0 + i * 50.0 for i in range(30)],
        "high": [50100.0 + i * 50.0 for i in range(30)],
        "low": [49900.0 + i * 50.0 for i in range(30)],
        "close": [50050.0 + i * 50.0 for i in range(30)],
        "volume": [100.0] * 30,
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
        latest_price=51500.0,
    )


def test_market_agent_synchronous_evaluation():
    agent = MarketIntelligenceAgent()
    packet = create_dummy_packet()

    funding_data = {"funding_rate": 0.00015, "funding_rate_annualized": 16.425}
    funding_hist = pd.DataFrame({"funding_rate": [0.0001] * 20})
    oi_data = {"open_interest_contracts": 60000.0}
    oi_hist = pd.DataFrame({"sum_open_interest": [55000.0 + i * 150.0 for i in range(30)]})
    top_trader_df = pd.DataFrame({"long_short_ratio": [1.15] * 20})
    sentiment_data = {"value": 65, "classification": "Greed"}

    report = agent.evaluate_market_data(
        packet=packet,
        funding_data=funding_data,
        funding_hist=funding_hist,
        oi_data=oi_data,
        oi_hist=oi_hist,
        top_trader_df=top_trader_df,
        sentiment_data=sentiment_data,
    )

    assert report.symbol == "BTC/USDT"
    assert report.funding_rate == 0.00015
    assert report.fear_and_greed_index == 65
    assert report.positioning_quadrant in [
        PositioningQuadrant.LONG_ACCUMULATION,
        PositioningQuadrant.SHORT_COVERING,
        PositioningQuadrant.SHORT_ACCUMULATION,
        PositioningQuadrant.LONG_LIQUIDATION,
        PositioningQuadrant.BALANCED,
    ]


@pytest.mark.asyncio
async def test_market_agent_alert_on_crowding():
    agent = MarketIntelligenceAgent()
    packet = create_dummy_packet()

    # Mock extreme long crowding
    agent.derivatives_fetcher.fetch_funding_rate = AsyncMock(
        return_value={"funding_rate": 0.0008, "funding_rate_annualized": 87.6}
    )
    agent.derivatives_fetcher.fetch_funding_rate_history = AsyncMock(
        return_value=pd.DataFrame({"funding_rate": [0.0001] * 30})
    )
    agent.derivatives_fetcher.fetch_open_interest = AsyncMock(
        return_value={"open_interest_contracts": 80000.0}
    )
    agent.derivatives_fetcher.fetch_open_interest_history = AsyncMock(
        return_value=pd.DataFrame({"sum_open_interest": [50000.0 + i * 500.0 for i in range(30)]})
    )
    agent.derivatives_fetcher.fetch_top_trader_long_short_ratio = AsyncMock(
        return_value=pd.DataFrame({"long_short_ratio": [0.75] * 24})  # Top traders are short!
    )
    agent.sentiment_fetcher.fetch_fear_and_greed = AsyncMock(
        return_value={"value": 88, "classification": "Extreme Greed"}
    )

    alert_events = []
    event_bus.subscribe(EVENT_MARKET_INTELLIGENCE_ALERT, lambda a: alert_events.append(a))

    report = await agent.analyze_live(packet)

    assert report.crowding_bias == CrowdingBias.CROWDED_LONG
    assert report.crowding_penalty >= 0.25
    assert len(alert_events) >= 1
    assert alert_events[-1]["symbol"] == "BTC/USDT"
