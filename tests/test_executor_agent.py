"""Unit tests for TradeExecutionAgent (Agent #9 - Sprint 9)."""

import pytest
from agents.executor_agent import TradeExecutionAgent
from core.events import (
    EVENT_CIRCUIT_BREAKER_TRIPPED,
    EVENT_EMERGENCY_FLATTEN,
    EVENT_ORDER_INTENT,
    event_bus,
)
from core.types import ExecutionMode, OrderIntent, OrderRole, OrderStatus
from engine.paper_exchange import PaperExchange
from models.portfolio_tracker import PortfolioTracker


@pytest.fixture
def execution_agent(tmp_path):
    ex = PaperExchange(initial_balance_usd=10000.0)
    ex.set_current_price("BTC/USDT", 65000.0)
    tracker = PortfolioTracker(initial_equity=10000.0, state_file_path=str(tmp_path / "test_portfolio_state.json"))
    agent = TradeExecutionAgent(
        exchange=ex,
        portfolio_tracker=tracker,
        mode=ExecutionMode.PAPER,
    )
    return agent


@pytest.fixture
def sample_market_intent():
    return OrderIntent(
        intent_id="intent-exec-01",
        symbol="BTC/USDT",
        side="BUY",
        order_type="MARKET",
        quantity_asset=0.05,
        notional_usd=3250.0,
        limit_price=65000.0,
        stop_loss_price=63500.0,
        take_profit_price=67250.0,
        target_2r_price=69500.0,
        invalidation_price=63000.0,
        urgency="TAKER_AGGRESSIVE",
    )


def test_agent_initialization(execution_agent):
    status = execution_agent.get_status()
    assert status["execution_mode"] == "PAPER"
    assert status["total_orders_executed"] == 0
    assert status["active_positions_count"] == 0


def test_execute_order_intent_market_fill(execution_agent, sample_market_intent):
    bracket, report = execution_agent.execute_order_intent(sample_market_intent)
    assert report.status == OrderStatus.FILLED
    assert report.filled_qty == 0.05
    assert execution_agent.total_orders_executed >= 1

    # Position must be active
    assert len(execution_agent.bracket_manager.positions) == 1
    pos = list(execution_agent.bracket_manager.positions.values())[0]
    assert pos.quantity == 0.05
    assert pos.side == "LONG"


def test_event_bus_order_intent_subscription(execution_agent, sample_market_intent):
    initial_orders = execution_agent.total_orders_executed
    event_bus.publish(EVENT_ORDER_INTENT, sample_market_intent)

    assert execution_agent.total_orders_executed > initial_orders
    assert len(execution_agent.bracket_manager.positions) == 1


def test_price_update_and_portfolio_sync(execution_agent, sample_market_intent):
    execution_agent.execute_order_intent(sample_market_intent)

    # Market moves up to 66,000 -> check unrealized PnL in portfolio tracker
    execution_agent.on_price_update("BTC/USDT", current_price=66000.0)
    assert execution_agent.portfolio_tracker.unrealized_pnl > 0.0

    # Market rally hits TP1 (67,250) -> triggers scale-out and records realized PnL
    fills = execution_agent.on_price_update("BTC/USDT", current_price=67300.0, high_price=67300.0)
    assert any(f.role == OrderRole.TAKE_PROFIT_1 for f in fills)
    # Check that realized trade was recorded
    assert len(execution_agent.portfolio_tracker.trade_history) >= 1
    assert execution_agent.portfolio_tracker.trade_history[-1]["net_pnl"] > 0.0


def test_emergency_flatten_event(execution_agent, sample_market_intent):
    execution_agent.execute_order_intent(sample_market_intent)
    assert len(execution_agent.bracket_manager.positions) == 1

    # Trigger emergency flatten event
    event_bus.publish(EVENT_EMERGENCY_FLATTEN, "BTC/USDT")

    # Inventory must now be 0
    pos = list(execution_agent.bracket_manager.positions.values())[0]
    assert pos.quantity == 0.0


def test_circuit_breaker_flatten_event(execution_agent, sample_market_intent):
    execution_agent.execute_order_intent(sample_market_intent)
    assert len(execution_agent.bracket_manager.positions) == 1

    # Trigger circuit breaker tripped event
    event_bus.publish(EVENT_CIRCUIT_BREAKER_TRIPPED, "DAILY_LOSS_EXCEEDED")

    pos = list(execution_agent.bracket_manager.positions.values())[0]
    assert pos.quantity == 0.0


def test_position_force_closed_after_max_hold(execution_agent, sample_market_intent):
    from datetime import datetime, timezone, timedelta

    execution_agent.execute_order_intent(sample_market_intent)
    pos = list(execution_agent.bracket_manager.positions.values())[0]
    assert pos.quantity > 0

    # Simulate position opened 75 hours ago (max_hold_candles=72)
    pos.opened_at = datetime.now(timezone.utc) - timedelta(hours=75)

    # Price update should trigger force close
    reports = execution_agent.on_price_update("BTC/USDT", current_price=65000.0)
    assert pos.quantity == 0.0
    assert any(r.role == OrderRole.EMERGENCY_FLATTEN for r in reports)


def test_position_alive_within_hold_limit(execution_agent, sample_market_intent):
    from datetime import datetime, timezone, timedelta

    execution_agent.execute_order_intent(sample_market_intent)
    pos = list(execution_agent.bracket_manager.positions.values())[0]
    assert pos.quantity > 0

    # Position opened 24 hours ago (well within 72h)
    pos.opened_at = datetime.now(timezone.utc) - timedelta(hours=24)

    # Price update within SL and TP range
    reports = execution_agent.on_price_update("BTC/USDT", current_price=65100.0)
    assert pos.quantity > 0

