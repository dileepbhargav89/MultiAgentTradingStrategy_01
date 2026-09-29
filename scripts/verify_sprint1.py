"""Sprint 1 End-to-End Verification Script.

Tests the full data foundation pipeline:
1. Generates multi-timeframe synthetic OHLCV data
2. Runs DataCleaner (gap filling, anomaly detection, quality scoring)
3. Runs FeatureEngineer (returns, log returns, volatility, ratios)
4. Runs DataQualityAgent (evaluates tradeability, checks veto power, cross-timeframe consistency)
5. Validates EventBus pub/sub notifications
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from loguru import logger
from agents.data_quality_agent import DataQualityAgent
from core.events import EVENT_DATA_QUALITY_HALT, EVENT_DATA_QUALITY_REPORT, event_bus
from core.types import AgentState
from data.cache_manager import CacheManager
from data.cleaner import DataCleaner
from data.features import FeatureEngineer


def create_mock_market_data() -> dict[str, pd.DataFrame]:
    """Generates synthetic healthy OHLCV data across 15m, 1h, 4h, 1d."""
    now = datetime.now(timezone.utc)
    tf_minutes = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    dataset = {}

    for tf, mins in tf_minutes.items():
        base_time = now - timedelta(minutes=100 * mins)
        price = 65000.0
        records = []
        for i in range(100):
            ts = base_time + timedelta(minutes=i * mins)
            records.append({
                "timestamp": ts,
                "open": price,
                "high": price * 1.004,
                "low": price * 0.996,
                "close": price * 1.001,
                "volume": 500.0 + (i % 5) * 50.0,
            })
            price = price * 1.001
        dataset[tf] = pd.DataFrame(records)

    return dataset


def main():
    print("=" * 65)
    print("🚀 STRATEGYONE - SPRINT 1 DATA FOUNDATION VERIFICATION")
    print("=" * 65)

    # 1. Test Event Bus
    event_log = []
    event_bus.subscribe(EVENT_DATA_QUALITY_REPORT, lambda r: event_log.append("REPORT_RECEIVED"))
    event_bus.subscribe(EVENT_DATA_QUALITY_HALT, lambda h: event_log.append("HALT_RECEIVED"))

    # 2. Generate Data
    print("\n[1/5] Generating multi-timeframe market dataset...")
    raw_data = create_mock_market_data()
    for tf, df in raw_data.items():
        print(f"  ✓ {tf:>3}: {len(df)} candles generated ({df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]})")

    # 3. Test Feature Engineering
    print("\n[2/5] Testing quantitative feature engineering...")
    fe = FeatureEngineer()
    features = fe.compute_all_timeframes(raw_data)
    for tf, fdf in features.items():
        assert "log_returns" in fdf.columns
        assert "volatility_24h" in fdf.columns
        assert "range_pct" in fdf.columns
        print(f"  ✓ {tf:>3}: {len(fdf.columns)} features calculated (vol_24h: {fdf['volatility_24h'].iloc[-1]:.6f})")

    # 4. Test Data Cleaning & Quality Evaluation
    print("\n[3/5] Testing Data Quality Agent on healthy data...")
    agent = DataQualityAgent()
    report = agent.evaluate_data("BTC/USDT", raw_data)

    print(f"  ✓ Agent Status:    {report.status.value}")
    print(f"  ✓ Overall Quality: {report.overall_quality:.2%}")
    print(f"  ✓ Tradeable:       {report.is_tradeable}")
    print(f"  ✓ Gaps Filled:     {report.gaps_filled}")
    print(f"  ✓ Anomalies:       {len(report.anomalies)}")
    assert report.status == AgentState.HEALTHY
    assert report.is_tradeable is True

    # 5. Test Cache Persistence
    print("\n[4/5] Testing Cache persistence...")
    cache = CacheManager(cache_dir="data/cache")
    cache.save("BTC/USDT", "1h", raw_data["1h"])
    loaded = cache.load("BTC/USDT", "1h")
    assert loaded is not None and len(loaded) == len(raw_data["1h"])
    print(f"  ✓ Cached and reloaded {len(loaded)} candles from disk")

    # 6. Test Veto Power on Corrupt Data
    print("\n[5/5] Testing Data Quality Agent VETO POWER on corrupted data...")
    corrupt_data = create_mock_market_data()
    # Inject corrupt candle
    corrupt_data["1h"].loc[10:25, "high"] = 1.0
    corrupt_data["1h"].loc[10:25, "low"] = 99999.0

    bad_report = agent.evaluate_data("BTC/USDT", corrupt_data)
    print(f"  ✓ Agent Status:    {bad_report.status.value}")
    print(f"  ✓ Overall Quality: {bad_report.overall_quality:.2%}")
    print(f"  ✓ Tradeable:       {bad_report.is_tradeable} (VETO ACTIVATED)")
    assert bad_report.status == AgentState.HALTED
    assert bad_report.is_tradeable is False
    assert "HALT_RECEIVED" in event_log

    print("\n" + "=" * 65)
    print("🎉 ALL SPRINT 1 ACCEPTANCE CRITERIA VERIFIED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    main()
