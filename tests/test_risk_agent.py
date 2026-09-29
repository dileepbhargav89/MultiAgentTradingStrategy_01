"""Unit tests for RiskManagementAgent (Sprint 7)."""

import numpy as np
import pytest
from agents.risk_agent import RiskManagementAgent
from core.events import EVENT_EMERGENCY_FLATTEN, event_bus
from core.types import (
    CrowdingBias,
    MarketIntelligenceReport,
    PositioningQuadrant,
    RiskLevel,
    StrategySpecies,
    TradeProposal,
    VolatilityRegime,
    VolatilityReport,
)
from models.portfolio_tracker import PortfolioTracker


@pytest.fixture
def mock_tracker(tmp_path):
    state_file = tmp_path / "risk_test_state.json"
    return PortfolioTracker(initial_equity=10000.0, state_file_path=str(state_file))


@pytest.fixture
def risk_agent(mock_tracker):
    return RiskManagementAgent(portfolio_tracker=mock_tracker)


@pytest.fixture
def sample_proposal():
    return TradeProposal(
        strategy_id="cand_test_01",
        species=StrategySpecies.MOMENTUM_TREND,
        action="BUY",
        symbol="BTC/USDT",
        entry_price=60000.0,
        stop_loss_price=58800.0,      # 2% stop distance ($1200)
        take_profit_price=62400.0,    # 4% profit target ($2400) -> 2.0 R:R
        confidence=0.75,
    )


def test_initial_risk_tier_green(risk_agent):
    assert risk_agent.current_risk_level == RiskLevel.GREEN
    assert risk_agent.get_allowed_size_multiplier() == 1.0


def test_state_machine_transitions_and_hysteresis(risk_agent):
    # Transition to YELLOW (DD = 3.5%)
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-350.0)
    tier = risk_agent._evaluate_state_machine()
    assert tier == RiskLevel.YELLOW
    assert risk_agent.get_allowed_size_multiplier() == 0.50

    # Test Hysteresis: DD drops to 2.5% (between 2.0% and 3.0%)
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-250.0)
    tier = risk_agent._evaluate_state_machine()
    assert tier == RiskLevel.YELLOW  # Must stay in YELLOW due to deadband

    # DD drops below 2.0% (DD = 1.5%) -> Should return to GREEN
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-150.0)
    tier = risk_agent._evaluate_state_machine()
    assert tier == RiskLevel.GREEN
    assert risk_agent.get_allowed_size_multiplier() == 1.0

    # Transition to ORANGE (DD = 6.0%)
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-600.0)
    tier = risk_agent._evaluate_state_machine()
    assert tier == RiskLevel.ORANGE
    assert risk_agent.get_allowed_size_multiplier() == 0.25

    # Transition to RED (DD = 8.5%)
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-850.0)
    tier = risk_agent._evaluate_state_machine()
    assert tier == RiskLevel.RED
    assert risk_agent.get_allowed_size_multiplier() == 0.0


def test_critical_drawdown_emergency_flatten(risk_agent):
    flatten_events = []
    def on_flatten(data):
        flatten_events.append(data)

    event_bus.subscribe(EVENT_EMERGENCY_FLATTEN, on_flatten)

    # DD = 11.0% breaches 10% critical threshold
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-1100.0)
    tier = risk_agent._evaluate_state_machine()
    assert tier == RiskLevel.CRITICAL
    assert len(flatten_events) >= 1
    assert flatten_events[0]["trigger"] == "CRITICAL_DRAWDOWN"


def test_audit_proposal_approved_in_green(risk_agent, sample_proposal):
    returns = np.random.normal(0.0005, 0.01, 100)
    assessment = risk_agent.audit_trade_proposal(
        proposal=sample_proposal,
        recent_returns=returns,
        proposed_position_usd=2000.0,
    )

    assert assessment.is_proposal_approved is True
    assert assessment.rejection_reason is None
    assert assessment.risk_level == RiskLevel.GREEN
    assert assessment.allowed_size_multiplier == 1.0
    assert assessment.dollar_risk_cap_usd == 150.0  # 1.5% of 10,000


def test_audit_proposal_veto_on_stop_loss_too_tight(risk_agent, sample_proposal):
    # Stop distance = 0.05% (< 0.2%)
    sample_proposal.stop_loss_price = 59970.0
    assessment = risk_agent.audit_trade_proposal(proposal=sample_proposal)

    assert assessment.is_proposal_approved is False
    assert "STOP_LOSS_TOO_TIGHT" in assessment.rejection_reason


def test_audit_proposal_veto_on_stop_loss_too_wide(risk_agent, sample_proposal):
    # Stop distance = 10% (> 8.0%)
    sample_proposal.stop_loss_price = 54000.0
    assessment = risk_agent.audit_trade_proposal(proposal=sample_proposal)

    assert assessment.is_proposal_approved is False
    assert "STOP_LOSS_TOO_WIDE" in assessment.rejection_reason


def test_audit_proposal_veto_on_insufficient_risk_reward(risk_agent, sample_proposal):
    # Risk = 1200 ($60k - $58.8k). Reward = 1000 ($61k - $60k). RR = 0.83 (< 1.40)
    sample_proposal.take_profit_price = 61000.0
    assessment = risk_agent.audit_trade_proposal(proposal=sample_proposal)

    assert assessment.is_proposal_approved is False
    assert "INSUFFICIENT_RISK_REWARD" in assessment.rejection_reason


def test_audit_proposal_veto_in_red_tier(risk_agent, sample_proposal):
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-850.0)  # 8.5% DD -> RED
    assessment = risk_agent.audit_trade_proposal(proposal=sample_proposal)

    assert assessment.is_proposal_approved is False
    assert "PORTFOLIO_DRAWDOWN_RESTRICTION" in assessment.rejection_reason


def test_audit_proposal_veto_on_squeeze(risk_agent, sample_proposal):
    market_rep = MarketIntelligenceReport(
        symbol="BTC/USDT",
        funding_rate=0.0006,
        funding_rate_annualized=65.7,
        funding_zscore=2.8,
        open_interest_usd=1.2e9,
        oi_change_4h_pct=4.5,
        oi_change_24h_pct=10.0,
        positioning_quadrant=PositioningQuadrant.LONG_ACCUMULATION,
        top_trader_long_short_ratio=1.8,
        fear_and_greed_index=85,
        fear_and_greed_label="Extreme Greed",
        crowding_bias=CrowdingBias.CROWDED_LONG,
        crowding_penalty=0.40,
        squeeze_warning="IMMINENT_LONG_SQUEEZE",
    )

    assessment = risk_agent.audit_trade_proposal(
        proposal=sample_proposal,
        market_report=market_rep,
    )

    assert assessment.is_proposal_approved is False
    assert "SQUEEZE_RISK_VETO" in assessment.rejection_reason


def test_dynamic_gross_exposure_scaling(risk_agent):
    # Baseline
    assert risk_agent.calculate_max_gross_exposure() == 0.50

    # Volatility chaos regime clamps to 20%
    vol_rep = VolatilityReport(
        symbol="BTC/USDT",
        forecasted_volatility_24h=75.0,
        parkinson_volatility=72.0,
        garman_klass_volatility=74.0,
        ewma_volatility=70.0,
        volatility_percentile=95.0,
        regime=VolatilityRegime.HIGH_VOL_CHAOS,
        volatility_multiplier=0.40,
        atr_stop_multiplier=2.5,
        is_breakout_imminent=False,
    )
    assert risk_agent.calculate_max_gross_exposure(volatility_report=vol_rep) == 0.20


def test_recovery_exit_path_a_full_hwm(risk_agent):
    # Transition to RED first
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-850.0)
    assert risk_agent._evaluate_state_machine() == RiskLevel.RED

    # Drop DD below 2% -> enters RECOVERY
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-150.0)
    assert risk_agent._evaluate_state_machine() == RiskLevel.RECOVERY
    assert risk_agent.tracker.recovery_entered_at is not None

    # Path A: 5 wins and equity >= HWM
    risk_agent.tracker.consecutive_recovery_wins = 5
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=0.0)
    assert risk_agent._evaluate_state_machine() == RiskLevel.GREEN
    assert risk_agent.tracker.recovery_entered_at is None


def test_recovery_exit_path_b_near_hwm(risk_agent):
    # Transition to RED first
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-850.0)
    risk_agent._evaluate_state_machine()

    # Drop DD below 2% -> enters RECOVERY
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-150.0)
    assert risk_agent._evaluate_state_machine() == RiskLevel.RECOVERY

    # Path B: 3 wins and equity >= 97% HWM (DD < 2% hysteresis threshold, e.g. DD = 1.5% = 98.5% of HWM)
    risk_agent.tracker.consecutive_recovery_wins = 3
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-150.0)
    assert risk_agent._evaluate_state_machine() == RiskLevel.GREEN


def test_recovery_exit_path_c_time_based(risk_agent):
    from datetime import datetime, timezone, timedelta

    # Transition to RED first
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-850.0)
    risk_agent._evaluate_state_machine()

    # Drop DD below 2% -> enters RECOVERY
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-150.0)
    assert risk_agent._evaluate_state_machine() == RiskLevel.RECOVERY

    # Path C: 48h elapsed and DD < 1%
    risk_agent.tracker.recovery_entered_at = datetime.now(timezone.utc) - timedelta(hours=49)
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-50.0)  # DD = 0.5% < 1%
    assert risk_agent._evaluate_state_machine() == RiskLevel.GREEN


def test_recovery_no_premature_exit(risk_agent):
    from datetime import datetime, timezone, timedelta

    # Transition to RED first
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-850.0)
    risk_agent._evaluate_state_machine()

    # Drop DD below 2% -> enters RECOVERY
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-150.0)
    assert risk_agent._evaluate_state_machine() == RiskLevel.RECOVERY

    # Only 1 win, only 24h elapsed, DD = 1.5% -> must stay in RECOVERY
    risk_agent.tracker.consecutive_recovery_wins = 1
    risk_agent.tracker.recovery_entered_at = datetime.now(timezone.utc) - timedelta(hours=24)
    risk_agent.tracker.update_unrealized_pnl(unrealized_pnl=-150.0)
    assert risk_agent._evaluate_state_machine() == RiskLevel.RECOVERY


def test_concentration_gate_blocks_third_position(risk_agent, sample_proposal):
    # Simulate 2 existing BTC/USDT positions
    risk_agent.tracker.update_open_positions([
        {"position_id": "pos-1", "symbol": "BTC/USDT", "quantity": 0.1},
        {"position_id": "pos-2", "symbol": "BTC/USDT", "quantity": 0.1},
    ])
    returns = np.random.normal(0.0005, 0.01, 100)
    assessment = risk_agent.audit_trade_proposal(
        proposal=sample_proposal,
        recent_returns=returns,
    )
    assert assessment.is_proposal_approved is False
    assert "CONCENTRATION_LIMIT_REACHED" in assessment.rejection_reason


def test_concentration_allows_different_symbol(risk_agent, sample_proposal):
    # 2 existing ETH/USDT positions, proposing BTC/USDT -> allowed
    risk_agent.tracker.update_open_positions([
        {"position_id": "pos-1", "symbol": "ETH/USDT", "quantity": 1.0},
        {"position_id": "pos-2", "symbol": "ETH/USDT", "quantity": 1.0},
    ])
    returns = np.random.normal(0.0005, 0.01, 100)
    assessment = risk_agent.audit_trade_proposal(
        proposal=sample_proposal,
        recent_returns=returns,
    )
    assert assessment.is_proposal_approved is True


