"""Unit tests for TradeDeciderAgent (Sprint 8)."""

import pytest
from agents.decider_agent import TradeDeciderAgent
from core.events import EVENT_ORDER_INTENT, EVENT_TRADE_DECISION, event_bus
from core.types import (
    AgentState,
    CrowdingBias,
    DataQualityReport,
    MarketBias,
    MarketIntelligenceReport,
    MoneyDecision,
    PositioningQuadrant,
    RiskAssessment,
    RiskLevel,
    StrategySpecies,
    TechnicalAnalysisReport,
    TradeProposal,
    VolatilityRegime,
    VolatilityReport,
)


@pytest.fixture
def decider_agent():
    return TradeDeciderAgent(consensus_threshold=0.65)


@pytest.fixture
def full_suite_reports():
    prop = TradeProposal(
        strategy_id="MOM-G1-champ",
        species=StrategySpecies.MOMENTUM_TREND,
        action="BUY",
        symbol="BTC/USDT",
        entry_price=64000.0,
        stop_loss_price=62720.0,      # 2% stop ($1280)
        take_profit_price=66880.0,    # 4.5% target (1.5R)
        target_2r_price=68800.0,      # 7.5% target (2.5R runner)
        invalidation_price=62500.0,
        execution_urgency="PASSIVE_MAKER",
        confidence=0.88,
    )
    dq = DataQualityReport(
        status=AgentState.HEALTHY,
        quality_scores={"15m": 1.0, "1h": 1.0},
        overall_quality=1.0,
        is_tradeable=True,
        freshness_ok=True,
    )
    tech = TechnicalAnalysisReport(
        symbol="BTC/USDT",
        bias=MarketBias.BULLISH,
        confluence_score=0.75,
        timeframe_scores={"15m": 0.7, "1h": 0.8},
        dimension_scores={"trend": 0.85, "momentum": 0.7},
        invalidation_price=62500.0,
    )
    mkt = MarketIntelligenceReport(
        symbol="BTC/USDT",
        funding_rate=0.0001,
        funding_rate_annualized=10.95,
        funding_zscore=0.3,
        open_interest_usd=1.1e9,
        oi_change_4h_pct=1.2,
        oi_change_24h_pct=2.8,
        positioning_quadrant=PositioningQuadrant.LONG_ACCUMULATION,
        top_trader_long_short_ratio=1.25,
        fear_and_greed_index=65,
        fear_and_greed_label="Greed",
        crowding_bias=CrowdingBias.BALANCED,
        crowding_penalty=0.0,
    )
    vol = VolatilityReport(
        symbol="BTC/USDT",
        forecasted_volatility_24h=30.0,
        parkinson_volatility=29.0,
        garman_klass_volatility=30.0,
        ewma_volatility=28.0,
        volatility_percentile=45.0,
        regime=VolatilityRegime.TRENDING_EXPANSION,
        volatility_multiplier=1.05,
        atr_stop_multiplier=1.8,
        is_breakout_imminent=False,
    )
    risk = RiskAssessment(
        risk_level=RiskLevel.GREEN,
        portfolio_equity=10000.0,
        high_water_mark=10000.0,
        drawdown_pct=0.0,
        daily_loss_pct=0.0,
        daily_loss_remaining_pct=0.03,
        weekly_loss_pct=0.0,
        var_95_1day_usd=120.0,
        cvar_95_1day_usd=200.0,
        current_exposure_pct=0.15,
        max_exposure_allowed_pct=0.50,
        consecutive_losses=0,
        circuit_breaker_active=False,
        is_proposal_approved=True,
        allowed_size_multiplier=1.0,
        dollar_risk_cap_usd=150.0,
    )
    money = MoneyDecision(
        strategy_id="MOM-G1-champ",
        symbol="BTC/USDT",
        action="BUY",
        position_size_usd=2000.0,
        position_size_asset=2000.0 / 64000.0,
        kelly_fraction_used=0.50,
        kelly_full_pct=0.40,
        kelly_suggested_pct=0.20,
        risk_adjusted_size_pct=0.20,
        dollar_risk_at_stop=40.0,
        dollar_risk_pct=0.004,
        fee_estimate_usd=2.0,
        fee_drag_ratio=18.0,
        is_sizing_approved=True,
    )
    return prop, dq, tech, mkt, vol, risk, money


def test_decider_full_consensus_dispatches_order_intent(decider_agent, full_suite_reports):
    prop, dq, tech, mkt, vol, risk, money = full_suite_reports
    order_intents = []
    trade_decisions = []
    event_bus.subscribe(EVENT_ORDER_INTENT, lambda oi: order_intents.append(oi))
    event_bus.subscribe(EVENT_TRADE_DECISION, lambda td: trade_decisions.append(td))

    final_dec, order_intent = decider_agent.evaluate_and_decide(
        proposal=prop,
        data_report=dq,
        tech_report=tech,
        market_report=mkt,
        vol_report=vol,
        risk_assessment=risk,
        money_decision=money,
    )

    assert final_dec.decision == "APPROVED"
    assert final_dec.consensus_score >= 0.75
    assert final_dec.approved_position_size_usd == 2000.0
    assert order_intent is not None
    assert order_intent.side == "BUY"
    assert order_intent.notional_usd == 2000.0
    assert order_intent.limit_price == 64000.0
    assert order_intent.stop_loss_price == 62720.0
    assert order_intent.take_profit_price == 66880.0
    assert order_intent.target_2r_price == 68800.0
    assert order_intent.order_type == "LIMIT"

    assert len(order_intents) >= 1
    assert len(trade_decisions) >= 1


def test_decider_veto_yields_no_order_intent(decider_agent, full_suite_reports):
    prop, dq, tech, mkt, vol, risk, money = full_suite_reports
    # Veto from Data Quality
    dq.is_tradeable = False
    dq.overall_quality = 0.60

    final_dec, order_intent = decider_agent.evaluate_and_decide(
        proposal=prop,
        data_report=dq,
        tech_report=tech,
        market_report=mkt,
        vol_report=vol,
        risk_assessment=risk,
        money_decision=money,
    )

    assert final_dec.decision == "REJECTED"
    assert final_dec.approved_position_size_usd == 0.0
    assert order_intent is None  # Never dispatch an order on veto!


def test_full_uuid_no_collision(decider_agent, full_suite_reports):
    prop, dq, tech, mkt, vol, risk, money = full_suite_reports
    intent_ids = set()
    for _ in range(50):
        _, order_intent = decider_agent.evaluate_and_decide(
            proposal=prop,
            data_report=dq,
            tech_report=tech,
            market_report=mkt,
            vol_report=vol,
            risk_assessment=risk,
            money_decision=money,
        )
        assert order_intent is not None
        assert len(order_intent.intent_id) == 39  # "intent-" + 32 hex digits
        intent_ids.add(order_intent.intent_id)
    assert len(intent_ids) == 50


def test_macro_trend_alignment_gate_veto(decider_agent, full_suite_reports):
    prop, dq, tech, mkt, vol, risk, money = full_suite_reports
    # Set technical bias to strong bullish
    tech.bias = MarketBias.STRONG_BULLISH
    tech.confluence_score = 0.80

    # Counter-trend proposal (SHORT in a BULL trend)
    prop.action = "SELL"

    final_dec, order_intent = decider_agent.evaluate_and_decide(
        proposal=prop,
        data_report=dq,
        tech_report=tech,
        market_report=mkt,
        vol_report=vol,
        risk_assessment=risk,
        money_decision=money,
    )

    assert final_dec.decision == "REJECTED"
    assert any("MACRO_TREND_VETO" in v for v in final_dec.vetoes_triggered)
    assert order_intent is None


