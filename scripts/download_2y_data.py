"""Download 2-year (730 days) historical BTC/USDT data across multiple timeframes."""

import asyncio
from datetime import datetime, timezone, timedelta
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from loguru import logger
from data.fetcher import DataFetcher

CACHE_DIR = PROJECT_ROOT / "data" / "cache"


async def download_timeframe(fetcher: DataFetcher, symbol: str, timeframe: str, days: int = 730) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{symbol.replace('/', '')}_{days}d_{timeframe}.csv"

    # Timeframe bar counts for 730 days (2 years)
    tf_bars_per_day = {
        "15m": 96,
        "1h": 24,
        "4h": 6,
        "1d": 1,
    }
    bars_per_day = tf_bars_per_day.get(timeframe, 24)
    total_bars = (days * bars_per_day) + 300  # margin for indicators and warmup

    logger.info(f"Downloading {total_bars} bars for {symbol} ({timeframe}) over {days} days (2 Years)...")

    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=days + 5)
    since_ms = int(start_time.timestamp() * 1000)

    df = await fetcher.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=total_bars, since=since_ms)

    if df.empty:
        logger.error(f"Failed to fetch data for {timeframe}")
        return df

    # Drop duplicates on timestamp and sort chronologically
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    df.to_csv(cache_file, index=False)
    logger.info(
        f"Saved {len(df)} candles to {cache_file} "
        f"({df.iloc[0]['timestamp']} to {df.iloc[-1]['timestamp']})"
    )
    return df


async def main():
    fetcher = DataFetcher(api_key="", api_secret="", testnet=False)
    symbol = "BTC/USDT"
    timeframes = ["1d", "4h", "1h", "15m"]

    try:
        for tf in timeframes:
            await download_timeframe(fetcher, symbol, tf, days=730)
            await asyncio.sleep(1.0)  # Rate limit courtesy
    finally:
        await fetcher.close()
    logger.info("All 2-year datasets (730 days) downloaded successfully!")


if __name__ == "__main__":
    asyncio.run(main())
