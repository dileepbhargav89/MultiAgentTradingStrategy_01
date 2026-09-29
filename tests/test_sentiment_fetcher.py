"""Unit tests for SentimentFetcher (Fear & Greed Index)."""

from datetime import datetime, timezone
import pytest
from data.sentiment_fetcher import SentimentFetcher


@pytest.mark.asyncio
async def test_sentiment_caching_and_structure():
    fetcher = SentimentFetcher(cache_ttl_seconds=3600)
    data1 = await fetcher.fetch_fear_and_greed()

    assert "value" in data1
    assert "classification" in data1
    assert 0 <= data1["value"] <= 100
    assert isinstance(data1["classification"], str)

    # Second call must hit cache
    data2 = await fetcher.fetch_fear_and_greed()
    assert data2["is_cached"] is True
    assert data2["value"] == data1["value"]


@pytest.mark.asyncio
async def test_sentiment_fallback_on_network_error():
    fetcher = SentimentFetcher()
    # Point to invalid URL
    fetcher.API_URL = "https://invalid-nonexistent-domain-12345.com/api"

    data = await fetcher.fetch_fear_and_greed()
    # Must gracefully return neutral 50
    assert data["value"] == 50
    assert data["classification"] == "Neutral"
