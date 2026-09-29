"""Unit tests for PaperExchange simulation engine (Sprint 9)."""

import pytest
from core.types import ExecutionMode, OrderRole, OrderStatus
from engine.paper_exchange import PaperExchange


@pytest.fixture
def paper_exchange():
    ex = PaperExchange(initial_balance_usd=10000.0)
    ex.set_current_price("BTC/USDT", 60000.0)
    return ex


def test_initial_balance_and_prices(paper_exchange):
    bal = paper_exchange.fetch_balance()
    assert bal["USDT"]["free"] == 10000.0
    assert paper_exchange.get_current_price("BTC/USDT") == 60000.0
    bid, ask = paper_exchange.get_bid_ask("BTC/USDT")
    assert bid < 60000.0 < ask


def test_market_order_immediate_fill_and_fee(paper_exchange):
    # Buy 0.1 BTC at market
    report = paper_exchange.create_order(
        symbol="BTC/USDT",
        order_type="MARKET",
        side="BUY",
        amount=0.1,
    )

    assert report.status == OrderStatus.FILLED
    assert report.filled_qty == 0.1
    assert report.fill_price > 0.0
    assert report.fee_paid_usd > 0.0
    assert report.execution_mode == ExecutionMode.PAPER

    # Check updated balances
    bal = paper_exchange.fetch_balance()
    assert bal["USDT"]["free"] < 10000.0
    assert bal["assets"]["BTC/USDT"] == 0.1


def test_post_only_limit_order_rejection(paper_exchange):
    bid, ask = paper_exchange.get_bid_ask("BTC/USDT")

    # Trying to BUY with limit price >= ask with post_only=True must be rejected
    report = paper_exchange.create_order(
        symbol="BTC/USDT",
        order_type="LIMIT",
        side="BUY",
        amount=0.1,
        price=ask + 50.0,
        params={"post_only": True},
    )
    assert report.status == OrderStatus.REJECTED
    assert report.filled_qty == 0.0


def test_resting_limit_order_fill_on_tick(paper_exchange):
    # Place resting Buy limit order below current market (e.g. 59,500)
    report = paper_exchange.create_order(
        symbol="BTC/USDT",
        order_type="LIMIT",
        side="BUY",
        amount=0.1,
        price=59500.0,
    )
    assert report.status == OrderStatus.OPEN

    # Tick at 59,800 -> still open
    fills_1 = paper_exchange.on_tick("BTC/USDT", current_price=59800.0)
    assert len(fills_1) == 0

    # Tick dips to 59,400 -> filled!
    fills_2 = paper_exchange.on_tick("BTC/USDT", current_price=59400.0, low_price=59400.0)
    assert len(fills_2) == 1
    assert fills_2[0].order_id == report.order_id
    assert fills_2[0].status == OrderStatus.FILLED
    assert fills_2[0].fill_price == 59500.0


def test_stop_loss_trigger_on_tick(paper_exchange):
    # Place a Stop Loss order at 58,000
    report = paper_exchange.create_order(
        symbol="BTC/USDT",
        order_type="STOP_MARKET",
        side="SELL",
        amount=0.1,
        params={"stopPrice": 58000.0},
        role=OrderRole.STOP_LOSS,
    )
    assert report.status == OrderStatus.OPEN

    # Price stays above stop
    fills = paper_exchange.on_tick("BTC/USDT", current_price=58500.0)
    assert len(fills) == 0

    # Price crosses stop (low dips to 57,900)
    fills = paper_exchange.on_tick("BTC/USDT", current_price=57900.0, low_price=57900.0)
    assert len(fills) == 1
    assert fills[0].status == OrderStatus.FILLED
    assert fills[0].role == OrderRole.STOP_LOSS


def test_cancel_order(paper_exchange):
    report = paper_exchange.create_order(
        symbol="BTC/USDT",
        order_type="LIMIT",
        side="BUY",
        amount=0.1,
        price=55000.0,
    )
    assert report.status == OrderStatus.OPEN

    c_report = paper_exchange.cancel_order(report.order_id, "BTC/USDT")
    assert c_report.status == OrderStatus.CANCELLED

    # Check open orders
    open_orders = paper_exchange.fetch_open_orders("BTC/USDT")
    assert len(open_orders) == 0
