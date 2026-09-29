"""Unit tests for DerivativesFetcher."""

from datetime import datetime, timezone
import pandas as pd
import pytest
from data.derivatives_fetcher import DerivativesFetcher


def test_format_symbol():
    fetcher = DerivativesFetcher()
    assert fetcher._format_symbol("BTC/USDT") == "BTCUSDT"
    assert fetcher._format_symbol("BTC/USDT:USDT") == "BTCUSDT"
    assert fetcher._format_symbol("ETH/USDT") == "ETHUSDT"


@pytest.mark.asyncio
async def test_fetch_funding_rate_structure():
    fetcher = DerivativesFetcher()
    data = await fetcher.fetch_funding_rate("BTC/USDT")

    assert "symbol" in data
    assert "funding_rate" in data
    assert "funding_rate_annualized" in data
    assert isinstance(data["funding_rate"], float)
    assert isinstance(data["funding_rate_annualized"], float)


@pytest.mark.asyncio
async def test_fetch_funding_rate_history():
    fetcher = DerivativesFetcher()
    df = await fetcher.fetch_funding_rate_history("BTC/USDT", limit=10)

    assert isinstance(df, pd.DataFrame)
    assert "timestamp" in df.columns
    assert "funding_rate" in df.columns
    assert len(df) == 10


@pytest.mark.asyncio
async def test_fetch_open_interest_structure():
    fetcher = DerivativesFetcher()
    data = await fetcher.fetch_open_interest("BTC/USDT")

    assert "symbol" in data
    assert "open_interest_contracts" in data
    assert data["open_interest_contracts"] > 0
