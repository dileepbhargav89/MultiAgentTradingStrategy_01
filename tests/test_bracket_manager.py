"""Unit tests for BracketOrderManager and OCO coordination (Sprint 9)."""

import pytest
from core.types import OrderIntent, OrderRole, OrderStatus
from engine.bracket_manager import BracketOrderManager
from engine.paper_exchange import PaperExchange


@pytest.fixture
def bracket_setup():
    ex = PaperExchange(initial_balance_usd=10000.0)
    ex.set_current_price("BTC/USDT", 60000.0)
    mgr = BracketOrderManager(ex)
    return ex, mgr


@pytest.fixture
def sample_intent():
    return OrderIntent(
        intent_id="intent-test-01",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity_asset=0.1,
        notional_usd=6000.0,
        limit_price=59900.0,
        stop_loss_price=58000.0,
        take_profit_price=62000.0,       # 1.5R target
        target_2r_price=64000.0,         # 2.5R runner target
        invalidation_price=57500.0,
        urgency="PASSIVE_MAKER",
    )


def test_bracket_pre_submission_invalidation_abort(bracket_setup, sample_intent):
    ex, mgr = bracket_setup
    # Set current market price below invalidation
    ex.set_current_price("BTC/USDT", 57000.0)

    bracket, report = mgr.submit_bracket_intent(sample_intent)
    assert report.status == OrderStatus.REJECTED
    assert bracket.parent_status == OrderStatus.REJECTED


def test_bracket_submission_and_fill_creates_sl_and_tp(bracket_setup, sample_intent):
    ex, mgr = bracket_setup
    ex.set_current_price("BTC/USDT", 60000.0)

    bracket, report = mgr.submit_bracket_intent(sample_intent)
    assert report.status == OrderStatus.OPEN
    assert bracket.parent_status == OrderStatus.OPEN

    # Now simulate market dipping to 59,800 to fill parent entry
    fills = mgr.handle_market_tick("BTC/USDT", current_price=59800.0, low_price=59800.0)
    assert len(fills) == 1
    assert fills[0].role == OrderRole.PARENT_ENTRY

    # Verify active position created
    assert len(mgr.positions) == 1
    pos = list(mgr.positions.values())[0]
    assert pos.quantity == 0.1
    assert pos.entry_price == 59900.0

    # Verify stop loss and TP orders are now registered in bracket
    assert bracket.stop_order_id is not None
    assert bracket.tp1_order_id is not None
    assert bracket.tp2_order_id is not None
    assert bracket.is_oco_active is True


def test_oco_stop_loss_fill_cancels_take_profits(bracket_setup, sample_intent):
    ex, mgr = bracket_setup
    ex.set_current_price("BTC/USDT", 60000.0)

    bracket, _ = mgr.submit_bracket_intent(sample_intent)
    # Fill parent entry
    mgr.handle_market_tick("BTC/USDT", current_price=59800.0, low_price=59800.0)

    # Now simulate crash to 57,900 crossing Stop Loss (58,000)
    sl_fills = mgr.handle_market_tick("BTC/USDT", current_price=57900.0, low_price=57900.0)
    assert any(f.role == OrderRole.STOP_LOSS for f in sl_fills)

    # TP1 and TP2 must be cancelled
    assert bracket.tp1_status == OrderStatus.CANCELLED
    assert bracket.tp2_status == OrderStatus.CANCELLED
    assert bracket.is_oco_active is False


def test_tp1_fill_scales_out_and_moves_stop_to_breakeven(bracket_setup, sample_intent):
    ex, mgr = bracket_setup
    ex.set_current_price("BTC/USDT", 60000.0)

    bracket, _ = mgr.submit_bracket_intent(sample_intent)
    # Fill parent entry
    mgr.handle_market_tick("BTC/USDT", current_price=59800.0, low_price=59800.0)

    pos = list(mgr.positions.values())[0]
    orig_sl = pos.stop_loss_price

    # Now simulate rally to TP1 (62,000)
    tp_fills = mgr.handle_market_tick("BTC/USDT", current_price=62100.0, high_price=62100.0)
    assert any(f.role == OrderRole.TAKE_PROFIT_1 for f in tp_fills)

    # Verify 50% scale-out executed
    assert pos.is_scale_out_executed is True
    assert pos.quantity == 0.05
    # Stop loss moved to entry price or cushioned profit lock
    assert pos.stop_loss_price >= pos.entry_price
    assert pos.stop_loss_price > orig_sl


def test_emergency_flatten_cancels_all_orders_and_flattens_position(bracket_setup, sample_intent):
    ex, mgr = bracket_setup
    ex.set_current_price("BTC/USDT", 60000.0)

    bracket, _ = mgr.submit_bracket_intent(sample_intent)
    # Fill parent entry to open position
    mgr.handle_market_tick("BTC/USDT", current_price=59800.0, low_price=59800.0)

    pos = list(mgr.positions.values())[0]
    assert pos.quantity == 0.1

    # Execute Emergency Flatten
    flatten_reports = mgr.emergency_flatten("BTC/USDT")
    assert any(r.role == OrderRole.EMERGENCY_FLATTEN for r in flatten_reports)

    # Position is completely liquidated
    assert pos.quantity == 0.0
    open_orders = ex.fetch_open_orders("BTC/USDT")
    assert len(open_orders) == 0
