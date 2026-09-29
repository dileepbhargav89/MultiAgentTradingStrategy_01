"""Unit tests for ConsensusMatrixEngine (Sprint 8)."""

import pytest
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
from models.consensus_matrix import ConsensusMatrixEngine


@pytest.fixture
def base_proposal():
    return TradeProposal(
        strategy_id="cand_test_01",
        species=StrategySpecies.MOMENTUM_TREND,
        action="BUY",
        symbol="BTC/USDT",
        entry_price=60000.0,
        stop_loss_price=58800.0,
        take_profit_price=63600.0,
        confidence=0.85,
    )


@pytest.fixture
def mock_reports():
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
        confluence_score=0.70,
        timeframe_scores={"15m": 0.6, "1h": 0.8},
        dimension_scores={"trend": 0.8, "momentum": 0.6},
        invalidation_price=58800.0,
    )
    mkt = MarketIntelligenceReport(
        symbol="BTC/USDT",
        funding_rate=0.0001,
        funding_rate_annualized=10.95,
        funding_zscore=0.5,
        open_interest_usd=1e9,
        oi_change_4h_pct=1.0,
        oi_change_24h_pct=3.0,
        positioning_quadrant=PositioningQuadrant.LONG_ACCUMULATION,
        top_trader_long_short_ratio=1.2,
        fear_and_greed_index=55,
        fear_and_greed_label="Neutral",
        crowding_bias=CrowdingBias.BALANCED,
        crowding_penalty=0.0,
    )
    vol = VolatilityReport(
        symbol="BTC/USDT",
        forecasted_volatility_24h=35.0,
        parkinson_volatility=34.0,
        garman_klass_volatility=35.0,
        ewma_volatility=33.0,
        volatility_percentile=50.0,
        regime=VolatilityRegime.TRENDING_EXPANSION,
        volatility_multiplier=1.0,
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
        var_95_1day_usd=100.0,
        cvar_95_1day_usd=180.0,
        current_exposure_pct=0.10,
        max_exposure_allowed_pct=0.50,
        consecutive_losses=0,
        circuit_breaker_active=False,
        is_proposal_approved=True,
        allowed_size_multiplier=1.0,
        dollar_risk_cap_usd=150.0,
    )
    money = MoneyDecision(
        strategy_id="cand_test_01",
        symbol="BTC/USDT",
        action="BUY",
        position_size_usd=1500.0,
        position_size_asset=0.025,
        kelly_fraction_used=0.50,
        kelly_full_pct=0.30,
        kelly_suggested_pct=0.15,
        risk_adjusted_size_pct=0.15,
        dollar_risk_at_stop=30.0,
        dollar_risk_pct=0.003,
        fee_estimate_usd=1.50,
        fee_drag_ratio=15.0,
        is_sizing_approved=True,
    )
    return dq, tech, mkt, vol, risk, money


def test_dynamic_weights_sentiment_and_vol_shifts(mock_reports):
    _, _, mkt, vol, _, _ = mock_reports
    # Baseline
    w_base = ConsensusMatrixEngine.compute_dynamic_weights(mkt, vol)
    assert abs(sum(w_base.values()) - 1.0) < 1e-6

    # Extreme Greed (FGI = 88)
    mkt.fear_and_greed_index = 88
    w_extreme = ConsensusMatrixEngine.compute_dynamic_weights(mkt, vol)
    assert w_extreme["market_intelligence"] > w_base["market_intelligence"]
    assert w_extreme["strategy_evolution"] < w_base["strategy_evolution"]

    # High Vol Chaos
    vol.regime = VolatilityRegime.HIGH_VOL_CHAOS
    w_chaos = ConsensusMatrixEngine.compute_dynamic_weights(mkt, vol)
    assert w_chaos["risk_management"] > w_base["risk_management"]


def test_boardroom_strong_consensus_approval(base_proposal, mock_reports):
    dq, tech, mkt, vol, risk, money = mock_reports
    res = ConsensusMatrixEngine.evaluate_boardroom_vote(
        proposal=base_proposal,
        data_report=dq,
        tech_report=tech,
        market_report=mkt,
        vol_report=vol,
        risk_assessment=risk,
        money_decision=money,
    )

    assert res["decision"] == "APPROVED"
    assert res["consensus_score"] >= 0.75
    assert len(res["vetoes_triggered"]) == 0
    assert len(res["conflicts_detected"]) == 0


def test_boardroom_rejection_on_risk_veto(base_proposal, mock_reports):
    dq, tech, mkt, vol, risk, money = mock_reports
    risk.is_proposal_approved = False
    risk.rejection_reason = "PORTFOLIO_DRAWDOWN_RESTRICTION"

    res = ConsensusMatrixEngine.evaluate_boardroom_vote(
        proposal=base_proposal,
        data_report=dq,
        tech_report=tech,
        market_report=mkt,
        vol_report=vol,
        risk_assessment=risk,
        money_decision=money,
    )

    assert res["decision"] == "REJECTED"
    assert any("RISK_AGENT_VETO" in v for v in res["vetoes_triggered"])


def test_boardroom_conflict_detection_technical_opposition(base_proposal, mock_reports):
    dq, tech, mkt, vol, risk, money = mock_reports
    # Strong technical bearish confluence opposing BUY proposal
    tech.confluence_score = -0.75

    res = ConsensusMatrixEngine.evaluate_boardroom_vote(
        proposal=base_proposal,
        data_report=dq,
        tech_report=tech,
        market_report=mkt,
        vol_report=vol,
        risk_assessment=risk,
        money_decision=money,
    )

    assert len(res["conflicts_detected"]) >= 1
    assert "TECHNICAL_DIRECTION_CONFLICT" in res["conflicts_detected"][0]
    # Decision must be downsized or rejected due to conflict penalty
    assert res["decision"] in ("DOWNSIZED", "REJECTED")


def test_strategy_capped_when_tech_neutral(base_proposal, mock_reports):
    dq, tech, mkt, vol, risk, money = mock_reports
    # Tech is neutral (confluence = 0.05 < 0.10)
    tech.confluence_score = 0.05
    base_proposal.confidence = 0.95

    res = ConsensusMatrixEngine.evaluate_boardroom_vote(
        proposal=base_proposal,
        data_report=dq,
        tech_report=tech,
        market_report=mkt,
        vol_report=vol,
        risk_assessment=risk,
        money_decision=money,
    )

    # Strategy vote should be capped at 0.60
    assert res["agent_votes"]["strategy_evolution"]["score"] == 0.60
    assert any("STRATEGY_TECH_FLOOR_CONFLICT" in c for c in res["conflicts_detected"])


def test_fgi_sigmoid_smooth_transition(mock_reports):
    dq, tech, mkt, vol, risk, money = mock_reports

    mkt.fear_and_greed_index = 22
    w_22 = ConsensusMatrixEngine.compute_dynamic_weights(market_report=mkt)

    mkt.fear_and_greed_index = 18
    w_18 = ConsensusMatrixEngine.compute_dynamic_weights(market_report=mkt)

    diff = abs(w_22["strategy_evolution"] - w_18["strategy_evolution"])
    assert diff < 0.02


