"""Unit tests for StrategyEvolutionAgent (Agent #5)."""

from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest

from agents.strategy_evolution_agent import StrategyEvolutionAgent
from core.events import EVENT_TRADE_PROPOSAL, event_bus
from core.types import (
    AgentState,
    DataPacket,
    DataQualityReport,
    MarketBias,
    StrategyGenome,
    StrategySpecies,
    TechnicalAnalysisReport,
    TradeProposal,
    VolatilityRegime,
    VolatilityReport,
)


def generate_packet(periods: int = 150) -> DataPacket:
    np.random.seed(55)
    closes = [65000.0]
    for _ in range(periods - 1):
        closes.append(closes[-1] * (1.0 + np.random.normal(0.0004, 0.003)))

    closes = np.array(closes)
    df = pd.DataFrame({
        "open": closes * 0.999,
        "high": closes * 1.002,
        "low": closes * 0.998,
        "close": closes,
        "volume": [1000.0] * periods,
    })

    dq_report = DataQualityReport(
        status=AgentState.HEALTHY,
        quality_scores={"1h": 1.0},
        overall_quality=1.0,
        is_tradeable=True,
        freshness_ok=True,
    )

    return DataPacket(
        symbol="BTC/USDT",
        timeframes={"1h": df, "15m": df, "4h": df, "1d": df},
        features={},
        quality=dq_report,
        latest_price=float(closes[-1]),
        spread_pct=0.0001,
    )


def test_agent_training_and_champion_installation():
    df = generate_packet().timeframes["1h"]
    agent = StrategyEvolutionAgent(population_size=20, tournament_k=2)

    champion = agent.train(df, generations=2, regime=VolatilityRegime.TRENDING_EXPANSION)

    assert champion is not None
    assert agent.active_champion == champion
    assert agent.latest_wf_report is not None
    assert agent.latest_mc_report is not None


def test_agent_evaluate_live_generates_trade_proposal():
    packet = generate_packet()
    agent = StrategyEvolutionAgent(population_size=20, tournament_k=2)

    trade_proposals = []
    event_bus.subscribe(EVENT_TRADE_PROPOSAL, lambda p: trade_proposals.append(p))

    # Mock upstream reports
    vol_report = VolatilityReport(
        symbol="BTC/USDT",
        forecasted_volatility_24h=50.0,
        parkinson_volatility=40.0,
        garman_klass_volatility=42.0,
        ewma_volatility=41.0,
        volatility_percentile=60.0,
        regime=VolatilityRegime.TRENDING_EXPANSION,
        volatility_multiplier=1.0,
        atr_stop_multiplier=1.5,
        is_breakout_imminent=False,
    )
    agent._on_volatility_report(vol_report)

    proposal = agent.evaluate_live(packet)

    assert isinstance(proposal, TradeProposal)
    assert proposal.symbol == "BTC/USDT"
    assert proposal.action in {"BUY", "SELL", "HOLD"}
    assert proposal.entry_price > 0
    assert proposal.stop_loss_price > 0
    assert proposal.take_profit_price > 0
    assert proposal.target_2r_price > 0
    assert len(trade_proposals) >= 1


def test_evolvable_entry_threshold(monkeypatch):
    from engine.species_strategies import SpeciesStrategyBuilder
    packet = generate_packet()
    agent = StrategyEvolutionAgent(population_size=10, tournament_k=2)

    # Champion with high threshold 0.80
    champion = StrategyGenome(
        strategy_id="test_champ",
        species=StrategySpecies.MOMENTUM_TREND,
        entry_signal_threshold=0.80,
    )
    agent.active_champion = champion

    # Mock signal builder to output 0.65 (which is > 0.50 but < 0.80)
    monkeypatch.setattr(SpeciesStrategyBuilder, "generate_signals", lambda df, g: np.full(len(df), 0.65))

    proposal = agent.evaluate_live(packet)
    # Since 0.65 < 0.80, action should be HOLD, not BUY!
    assert proposal.action == "HOLD"

    # Now lower threshold to 0.60
    champion.entry_signal_threshold = 0.60
    proposal2 = agent.evaluate_live(packet)
    # Since 0.65 > 0.60, action should be BUY!
    assert proposal2.action == "BUY"

