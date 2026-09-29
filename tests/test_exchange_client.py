"""Unit tests for BinanceExchangeClient precision formatting and lot sizing safeguards (Sprint 9)."""

import pytest
from engine.exchange_client import BinanceExchangeClient


@pytest.fixture
def exchange_client():
    # Initialize in sandbox testnet mode
    return BinanceExchangeClient(api_key="mock_key", api_secret="mock_secret", testnet=True)


def test_format_price_tick_size(exchange_client):
    # Default BTC tick size is 0.01
    formatted = exchange_client.format_price("BTC/USDT", 65432.12648)
    assert formatted == 65432.13

    formatted_round = exchange_client.format_price("BTC/USDT", 65432.10111)
    assert formatted_round == 65432.10


def test_format_quantity_step_size(exchange_client):
    # Quantity must floor down to stepSize (e.g. 0.001) to prevent insufficient balance
    formatted = exchange_client.format_quantity("BTC/USDT", 0.1239999)
    assert formatted == 0.123

    formatted_exact = exchange_client.format_quantity("BTC/USDT", 0.050)
    assert formatted_exact == 0.05


def test_check_min_notional(exchange_client):
    # Minimum notional requirement is $10.00
    valid, notional = exchange_client.check_min_notional("BTC/USDT", price=60000.0, quantity=0.001)
    assert valid is True
    assert notional == 60.0

    invalid, small_notional = exchange_client.check_min_notional("BTC/USDT", price=60000.0, quantity=0.00005)
    assert invalid is False
    assert small_notional == 3.0
