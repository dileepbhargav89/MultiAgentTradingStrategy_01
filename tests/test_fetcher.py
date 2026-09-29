"""Tests for DataFetcher pagination, retry backoff, and weight tracking using mocked CCXT exchange."""

import asyncio
from unittest.mock import AsyncMock, patch
import ccxt.async_support as ccxt_async
import pytest
from data.fetcher import DataFetcher


@pytest.mark.asyncio
async def test_fetch_returns_dataframe_with_correct_columns():
    fetcher = DataFetcher(exchange_id="binance", testnet=True)
    # Mock exchange response
    fake_candles = [
        [1700000000000, 50000.0, 50500.0, 49800.0, 50200.0, 150.0],
        [1700003600000, 50200.0, 50800.0, 50100.0, 50600.0, 180.0],
    ]
    fetcher.exchange.fetch_ohlcv = AsyncMock(return_value=fake_candles)

    df = await fetcher.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=2)
    await fetcher.close()

    expected_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    assert list(df.columns) == expected_cols
    assert len(df) == 2
    assert df["close"].iloc[1] == 50600.0


@pytest.mark.asyncio
async def test_fetch_handles_pagination():
    fetcher = DataFetcher(exchange_id="binance", testnet=True)

    # 1st call returns 1000 candles, 2nd call returns 500 candles
    base_ts = 1700000000000
    tf_ms = 3600000
    batch1 = [[base_ts + i * tf_ms, 50000.0, 50100.0, 49900.0, 50050.0, 10.0] for i in range(1000)]
    batch2 = [[base_ts + (1000 + i) * tf_ms, 50050.0, 50200.0, 50000.0, 50150.0, 12.0] for i in range(500)]

    fetcher.exchange.fetch_ohlcv = AsyncMock(side_effect=[batch1, batch2])

    df = await fetcher.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=1500)
    await fetcher.close()

    assert len(df) == 1500
    assert fetcher.exchange.fetch_ohlcv.call_count == 2


@pytest.mark.asyncio
async def test_fetch_respects_rate_limits():
    fetcher = DataFetcher(exchange_id="binance", testnet=True)
    assert fetcher.get_weight_used() == 0

    fake_candles = [[1700000000000, 50000.0, 50100.0, 49900.0, 50050.0, 10.0]]
    fetcher.exchange.fetch_ohlcv = AsyncMock(return_value=fake_candles)

    await fetcher.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=1)
    await fetcher.close()

    # Weight should have recorded 2 units
    assert fetcher.get_weight_used() == 2


@pytest.mark.asyncio
async def test_fetch_retries_on_network_error():
    fetcher = DataFetcher(exchange_id="binance", testnet=True)

    fake_candles = [[1700000000000, 50000.0, 50100.0, 49900.0, 50050.0, 10.0]]
    # Fail first 2 attempts with NetworkError, succeed on 3rd attempt
    fetcher.exchange.fetch_ohlcv = AsyncMock(
        side_effect=[
            ccxt_async.NetworkError("Connection reset"),
            ccxt_async.RequestTimeout("Timeout"),
            fake_candles,
        ]
    )

    df = await fetcher.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=1, max_retries=3)
    await fetcher.close()

    assert len(df) == 1
    assert fetcher.exchange.fetch_ohlcv.call_count == 3


@pytest.mark.asyncio
async def test_fetch_spread():
    fetcher = DataFetcher(exchange_id="binance", testnet=True)
    fetcher.exchange.fetch_ticker = AsyncMock(
        return_value={"bid": 50000.0, "ask": 50010.0, "last": 50005.0}
    )

    spread_data = await fetcher.fetch_spread("BTC/USDT")
    await fetcher.close()

    assert spread_data["bid"] == 50000.0
    assert spread_data["ask"] == 50010.0
    assert spread_data["spread"] == 10.0
    assert pytest.approx(spread_data["spread_pct"], 1e-6) == 10.0 / 50000.0
