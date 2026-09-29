"""Unit tests for MoneyManagementAgent (Sprint 8)."""

import pytest
from agents.money_agent import MoneyManagementAgent
from core.events import EVENT_MONEY_DECISION, event_bus
from core.types import (
    RiskAssessment,
    RiskLevel,
    StrategySpecies,
    TradeProposal,
)


@pytest.fixture
def money_agent():
    return MoneyManagementAgent(reserve_ratio=0.40, kelly_fraction=0.50)


@pytest.fixture
def sample_proposal():
    return TradeProposal(
        strategy_id="cand_test_01",
        species=StrategySpecies.MOMENTUM_TREND,
        action="BUY",
        symbol="BTC/USDT",
        entry_price=60000.0,
        stop_loss_price=58800.0,      # 2% stop distance
        take_profit_price=63600.0,    # 6% target
        confidence=0.80,
        win_rate=0.60,
        profit_factor=2.0,
    )


@pytest.fixture
def approved_risk_assessment():
    return RiskAssessment(
        risk_level=RiskLevel.GREEN,
        portfolio_equity=10000.0,
        high_water_mark=10000.0,
        drawdown_pct=0.0,
        daily_loss_pct=0.0,
        daily_loss_remaining_pct=0.03,
        weekly_loss_pct=0.0,
        var_95_1day_usd=150.0,
        cvar_95_1day_usd=250.0,
        current_exposure_pct=0.20,     # $2,000 already deployed
        max_exposure_allowed_pct=0.50,
        consecutive_losses=0,
        circuit_breaker_active=False,
        is_proposal_approved=True,
        allowed_size_multiplier=1.0,
        dollar_risk_cap_usd=150.0,
    )


def test_money_agent_normal_sizing_approved(money_agent, sample_proposal, approved_risk_assessment):
    dec = money_agent.evaluate_position_size(
        proposal=sample_proposal,
        risk_assessment=approved_risk_assessment,
    )

    assert dec.is_sizing_approved is True
    assert dec.rejection_reason is None
    assert dec.reserve_capital_usd == 4000.0   # 40% reserve
    assert dec.available_capital_usd == 6000.0 # 60% deployable
    assert dec.position_size_usd > 50.0
    assert dec.dollar_risk_at_stop <= 150.0    # Capped at 1.5% of 10,000
    assert dec.fee_drag_ratio >= 3.0


def test_money_agent_rejection_on_upstream_risk_veto(money_agent, sample_proposal, approved_risk_assessment):
    approved_risk_assessment.is_proposal_approved = False
    approved_risk_assessment.rejection_reason = "PORTFOLIO_DRAWDOWN_RESTRICTION"

    dec = money_agent.evaluate_position_size(
        proposal=sample_proposal,
        risk_assessment=approved_risk_assessment,
    )

    assert dec.is_sizing_approved is False
    assert "UPSTREAM_RISK_GATE_REJECTED" in dec.rejection_reason
    assert dec.position_size_usd == 0.0


def test_money_agent_reserve_headroom_downscale(money_agent, sample_proposal, approved_risk_assessment):
    # If 55% is already deployed, only 5% ($500) remains to hit the 60% deployable ceiling
    approved_risk_assessment.current_exposure_pct = 0.55

    dec = money_agent.evaluate_position_size(
        proposal=sample_proposal,
        risk_assessment=approved_risk_assessment,
    )

    assert dec.is_sizing_approved is True
    # Size must be clamped to the remaining $500 headroom
    assert dec.position_size_usd <= 500.01


def test_money_agent_event_publishing(money_agent, sample_proposal, approved_risk_assessment):
    events = []
    event_bus.subscribe(EVENT_MONEY_DECISION, lambda d: events.append(d))

    money_agent.evaluate_position_size(
        proposal=sample_proposal,
        risk_assessment=approved_risk_assessment,
    )

    assert len(events) >= 1
    assert events[-1].symbol == "BTC/USDT"


def test_kelly_conservative_fallback_unproven(money_agent, approved_risk_assessment):
    unproven_proposal = TradeProposal(
        strategy_id="cand_unproven_01",
        species=StrategySpecies.MOMENTUM_TREND,
        action="BUY",
        symbol="BTC/USDT",
        entry_price=60000.0,
        stop_loss_price=58800.0,
        take_profit_price=63600.0,
        confidence=0.50,
        win_rate=0.0,
        profit_factor=0.0,
    )
    dec = money_agent.evaluate_position_size(
        proposal=unproven_proposal,
        risk_assessment=approved_risk_assessment,
    )
    assert dec.is_sizing_approved is True

    proven_proposal = TradeProposal(
        strategy_id="cand_proven_01",
        species=StrategySpecies.MOMENTUM_TREND,
        action="BUY",
        symbol="BTC/USDT",
        entry_price=60000.0,
        stop_loss_price=58800.0,
        take_profit_price=63600.0,
        confidence=0.80,
        win_rate=0.60,
        profit_factor=2.0,
    )
    dec_proven = money_agent.evaluate_position_size(
        proposal=proven_proposal,
        risk_assessment=approved_risk_assessment,
    )
    assert dec.position_size_usd < dec_proven.position_size_usd

