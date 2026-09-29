"""Binance OHLCV data fetcher using CCXT with pagination, retries, and rate tracking."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import ccxt.async_support as ccxt_async
import numpy as np
import pandas as pd
from loguru import logger
from config.settings import get_settings


TIMEFRAME_MS = {
    "1m": 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "30m": 30 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "2h": 2 * 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "8h": 8 * 60 * 60 * 1000,
    "12h": 12 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
    "1w": 7 * 24 * 60 * 60 * 1000,
}


class DataFetcher:
    """
    Fetches OHLCV data from Binance via CCXT.
    Features:
    - Automatic pagination for arbitrarily deep historical lookback
    - Resilient retry logic with exponential backoff
    - API weight tracking to avoid exchange rate limits
    - Normalized pandas DataFrame output: [timestamp, open, high, low, close, volume]
    """

    def __init__(
        self,
        exchange_id: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: Optional[bool] = None,
    ) -> None:
        self.settings = get_settings()
        self.exchange_id = exchange_id or self.settings.EXCHANGE
        self.api_key = api_key if api_key is not None else self.settings.API_KEY
        self.api_secret = api_secret if api_secret is not None else self.settings.API_SECRET
        self.testnet = testnet if testnet is not None else self.settings.TESTNET

        exchange_class = getattr(ccxt_async, self.exchange_id, None)
        if not exchange_class:
            raise ValueError(f"Exchange '{self.exchange_id}' not supported by CCXT.")

        config = {
            "enableRateLimit": True,
            "timeout": 30000,
            "options": {"defaultType": "spot"},
        }
        if self.api_key:
            config["apiKey"] = self.api_key
        if self.api_secret:
            config["secret"] = self.api_secret
        self.exchange = exchange_class(config)
        if self.testnet:
            try:
                self.exchange.set_sandbox_mode(True)
            except Exception as e:
                logger.warning(f"Could not activate sandbox mode on {self.exchange_id}: {e}")

        self._weight_used: int = 0
        self._last_weight_reset: datetime = datetime.now(timezone.utc)

    def get_weight_used(self) -> int:
        """Returns the accumulated API weight used since last minute reset."""
        now = datetime.now(timezone.utc)
        if (now - self._last_weight_reset).total_seconds() >= 60:
            self._weight_used = 0
            self._last_weight_reset = now
        return self._weight_used

    def _record_weight(self, weight: int = 2) -> None:
        self.get_weight_used()  # Trigger potential reset
        self._weight_used += weight

    async def close(self) -> None:
        """Closes the underlying exchange HTTP session."""
        if self.exchange:
            await self.exchange.close()

    async def fetch_ticker(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Fetch real-time ticker data (last price, bid, ask, 24h volume)."""
        target_symbol = symbol or self.settings.SYMBOL
        try:
            ticker = await self.exchange.fetch_ticker(target_symbol)
            self._record_weight(1)
            return ticker or {}
        except Exception as e:
            logger.warning(f"Error fetching ticker for {target_symbol}: {e}")
            return {}

    async def fetch_spread(self, symbol: Optional[str] = None) -> Dict[str, float]:
        """Fetch current bid-ask spread and relative spread percentage."""
        ticker = await self.fetch_ticker(symbol)
        bid = float(ticker.get("bid") or 0.0)
        ask = float(ticker.get("ask") or 0.0)
        last = float(ticker.get("last") or ticker.get("close") or 0.0)

        spread = max(0.0, ask - bid) if (bid > 0 and ask > 0) else 0.0
        spread_pct = (spread / bid) if bid > 0 else 0.0

        return {
            "bid": bid,
            "ask": ask,
            "last": last,
            "spread": spread,
            "spread_pct": spread_pct,
        }

    async def fetch_ohlcv(
        self,
        symbol: Optional[str] = None,
        timeframe: str = "1h",
        limit: int = 1000,
        since: Optional[int] = None,
        max_retries: int = 3,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candles with automatic backward pagination and retries.

        Returns DataFrame columns:
        ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        """
        target_symbol = symbol or self.settings.SYMBOL
        tf_ms = TIMEFRAME_MS.get(timeframe, 60 * 60 * 1000)

        # If since not explicitly provided, calculate start timestamp to cover limit
        if since is None:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            since = now_ms - (limit * tf_ms)

        all_candles: List[list] = []
        batch_limit = 1000  # Binance max per request
        current_since = since
        last_seen_ts = -1

        while len(all_candles) < limit:
            remaining = limit - len(all_candles)
            fetch_count = min(remaining, batch_limit)

            candles = await self._fetch_batch_with_retry(
                target_symbol, timeframe, current_since, fetch_count, max_retries
            )

            if not candles:
                break

            all_candles.extend(candles)
            self._record_weight(5 if fetch_count > 500 else 2)

            last_timestamp = candles[-1][0]
            if last_timestamp <= last_seen_ts:
                # No forward progress made
                break
            last_seen_ts = last_timestamp
            current_since = last_timestamp + 1

        if not all_candles:
            logger.warning(f"No candles returned for {target_symbol} {timeframe}")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(
            all_candles,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)

        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        # Keep the latest `limit` candles
        if len(df) > limit:
            df = df.iloc[-limit:].reset_index(drop=True)

        return df

    async def _fetch_batch_with_retry(
        self,
        symbol: str,
        timeframe: str,
        since: int,
        limit: int,
        max_retries: int = 3,
    ) -> List[list]:
        """Fetch a single batch of candles with exponential backoff."""
        attempt = 0
        backoff_sec = 1.0

        while attempt < max_retries:
            try:
                candles = await self.exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    since=since,
                    limit=limit,
                )
                return candles or []
            except (ccxt_async.RateLimitExceeded, ccxt_async.DDoSProtection) as e:
                attempt += 1
                logger.warning(f"Rate limit exceeded fetching {symbol} {timeframe}: {e}. Backing off {backoff_sec * 5}s...")
                await asyncio.sleep(backoff_sec * 5)
                backoff_sec *= 2
            except (ccxt_async.NetworkError, ccxt_async.RequestTimeout) as e:
                attempt += 1
                logger.warning(f"Network error fetching {symbol} {timeframe} (attempt {attempt}/{max_retries}): {e}")
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(backoff_sec)
                backoff_sec *= 2
            except ccxt_async.ExchangeError as e:
                logger.error(f"Exchange error fetching {symbol} {timeframe}: {e}")
                raise
            except Exception as e:
                attempt += 1
                logger.error(f"Unexpected error fetching {symbol} {timeframe}: {e}")
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(backoff_sec)
                backoff_sec *= 2

        return []

    async def fetch_all_timeframes(
        self,
        symbol: Optional[str] = None,
        timeframes: Optional[List[str]] = None,
        candle_limits: Optional[Dict[str, int]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch OHLCV candles for all configured timeframes concurrently.
        """
        target_symbol = symbol or self.settings.SYMBOL
        active_tfs = timeframes or self.settings.TIMEFRAMES
        limits = candle_limits or self.settings.CANDLE_LIMITS

        tasks = [
            self.fetch_ohlcv(
                symbol=target_symbol,
                timeframe=tf,
                limit=limits.get(tf, 1000)
            )
            for tf in active_tfs
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        timeframe_dfs: Dict[str, pd.DataFrame] = {}

        for tf, res in zip(active_tfs, results):
            if isinstance(res, Exception):
                logger.error(f"Failed to fetch timeframe {tf} for {target_symbol}: {res}")
                timeframe_dfs[tf] = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
            else:
                timeframe_dfs[tf] = res

        return timeframe_dfs
