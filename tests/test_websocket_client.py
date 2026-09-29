"""Unit tests for BinanceWebSocketClient (Sprint 11)."""

import json
from unittest.mock import MagicMock
import pytest

from core.events import EVENT_CANDLE_CLOSED, EVENT_MARKET_TICK, event_bus
from data.websocket_client import BinanceWebSocketClient


def test_websocket_url_generation():
    """Validates URL generation for live and testnet environments."""
    client_live = BinanceWebSocketClient(symbol="BTC/USDT", timeframe="15m", testnet=False)
    assert "stream.binance.com:9443/stream" in client_live.url
    assert "streams=btcusdt@bookTicker/btcusdt@kline_15m" in client_live.url

    client_testnet = BinanceWebSocketClient(symbol="ETH/USDT", timeframe="1h", testnet=True)
    assert "stream.binance.vision:9443/stream" in client_testnet.url
    assert "streams=ethusdt@bookTicker/ethusdt@kline_1h" in client_testnet.url


def test_book_ticker_message_parsing():
    """Tests parsing of bookTicker messages and event emission."""
    tick_received = []

    def on_tick_cb(payload):
        tick_received.append(payload)

    client = BinanceWebSocketClient(symbol="BTC/USDT", on_tick=on_tick_cb)

    # Subscribe listener to event bus
    bus_ticks = []
    event_bus.subscribe(EVENT_MARKET_TICK, lambda d: bus_ticks.append(d))

    raw_msg = json.dumps({
        "stream": "btcusdt@bookTicker",
        "data": {
            "u": 1234567,
            "s": "BTCUSDT",
            "b": "65000.00",
            "B": "1.25",
            "a": "65000.50",
            "A": "2.10",
        }
    })

    client._handle_message(raw_msg)

    assert client.latest_tick is not None
    assert client.latest_tick["bid"] == 65000.00
    assert client.latest_tick["ask"] == 65000.50
    assert client.latest_tick["price"] == 65000.25
    assert len(tick_received) == 1
    assert len(bus_ticks) >= 1


def test_kline_intermediate_and_closed_parsing():
    """Tests that kline updates are cached and EVENT_CANDLE_CLOSED only fires when candle closes."""
    candle_closed_events = []
    event_bus.subscribe(EVENT_CANDLE_CLOSED, lambda d: candle_closed_events.append(d))

    client = BinanceWebSocketClient(symbol="BTC/USDT", timeframe="15m")

    # 1. Intermediate unclosed candle
    unclosed_msg = json.dumps({
        "stream": "btcusdt@kline_15m",
        "data": {
            "e": "kline",
            "k": {
                "t": 100000,
                "T": 100899,
                "s": "BTCUSDT",
                "i": "15m",
                "o": "65100.00",
                "c": "65250.00",
                "h": "65300.00",
                "l": "65050.00",
                "v": "15.4",
                "x": False,
            }
        }
    })
    client._handle_message(unclosed_msg)
    assert client.latest_kline is not None
    assert client.latest_kline["close"] == 65250.00
    assert client.latest_kline["is_closed"] is False
    assert len(candle_closed_events) == 0

    # 2. Closed candle
    closed_msg = json.dumps({
        "stream": "btcusdt@kline_15m",
        "data": {
            "e": "kline",
            "k": {
                "t": 100000,
                "T": 100899,
                "s": "BTCUSDT",
                "i": "15m",
                "o": "65100.00",
                "c": "65280.00",
                "h": "65320.00",
                "l": "65050.00",
                "v": "28.9",
                "x": True,
            }
        }
    })
    client._handle_message(closed_msg)
    assert client.latest_kline["is_closed"] is True
    assert len(candle_closed_events) == 1
    assert candle_closed_events[0]["close"] == 65280.00
