"""Tests for CacheManager disk caching."""

import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import pytest
from data.cache_manager import CacheManager


@pytest.fixture
def temp_cache_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_cache_save_and_load(temp_cache_dir):
    cache = CacheManager(cache_dir=temp_cache_dir)
    now = datetime.now(timezone.utc)
    df = pd.DataFrame({
        "timestamp": [now - timedelta(hours=1), now],
        "open": [50000.0, 50100.0],
        "high": [50200.0, 50300.0],
        "low": [49900.0, 50050.0],
        "close": [50100.0, 50250.0],
        "volume": [10.5, 12.0],
    })

    cache.save("BTC/USDT", "1h", df)
    loaded = cache.load("BTC/USDT", "1h")

    assert loaded is not None
    assert len(loaded) == 2
    assert "timestamp" in loaded.columns
    assert loaded["close"].iloc[1] == 50250.0


def test_cache_update_merge(temp_cache_dir):
    cache = CacheManager(cache_dir=temp_cache_dir)
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc)

    df1 = pd.DataFrame({
        "timestamp": [t0, t1],
        "open": [100.0, 101.0],
        "high": [102.0, 103.0],
        "low": [99.0, 100.0],
        "close": [101.0, 102.0],
        "volume": [10.0, 15.0],
    })
    cache.save("BTC/USDT", "1h", df1)

    df2 = pd.DataFrame({
        "timestamp": [t1, t2],  # t1 overlaps
        "open": [101.0, 102.0],
        "high": [103.0, 104.0],
        "low": [100.0, 101.0],
        "close": [102.0, 103.0],
        "volume": [15.0, 20.0],
    })

    merged = cache.update("BTC/USDT", "1h", df2)
    assert len(merged) == 3  # Deduped t0, t1, t2

    stats = cache.get_stats("BTC/USDT", "1h")
    assert stats["exists"] is True
    assert stats["candles"] == 3
    assert stats["size_kb"] > 0
