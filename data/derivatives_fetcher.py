"""Binance USD-M Futures derivatives data fetcher: Funding Rates, Open Interest, and Long/Short Ratio."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import aiohttp
import pandas as pd
from loguru import logger
from config.settings import get_settings


class DerivativesFetcher:
    """
    Fetches real-time and historical derivatives market data from Binance Futures public endpoints.
    Requires no private API keys for public market data.
    """

    BASE_URL = "https://fapi.binance.com"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None) -> None:
        self.settings = get_settings()
        self._session = session
        self._own_session = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "StrategyOne-TradingEngine/1.0"}
            )
            self._own_session = True
        return self._session

    async def close(self) -> None:
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    def _format_symbol(self, symbol: str) -> str:
        """Converts 'BTC/USDT' or 'BTC/USDT:USDT' to 'BTCUSDT'."""
        return symbol.replace("/", "").replace(":", "").split("USDT")[0] + "USDT"

    async def fetch_funding_rate(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetches latest 8h funding rate and next funding timestamp.
        """
        target_symbol = self._format_symbol(symbol or self.settings.SYMBOL)
        url = f"{self.BASE_URL}/fapi/v1/fundingRate?symbol={target_symbol}&limit=1"

        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list):
                        latest = data[-1]
                        rate = float(latest.get("fundingRate", 0.0001))
                        return {
                            "symbol": target_symbol,
                            "funding_rate": rate,
                            "funding_rate_annualized": rate * 3 * 365 * 100.0,  # 8h * 3 * 365
                            "funding_time": pd.to_datetime(latest.get("fundingTime", 0), unit="ms", utc=True),
                        }
        except Exception as e:
            logger.warning(f"Failed to fetch funding rate for {target_symbol}: {e}")

        # Baseline fallback: neutral 0.01% (10.95% APR)
        return {
            "symbol": target_symbol,
            "funding_rate": 0.0001,
            "funding_rate_annualized": 10.95,
            "funding_time": datetime.now(timezone.utc),
        }

    async def fetch_funding_rate_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 90,  # 90 entries * 8h = 30 days
    ) -> pd.DataFrame:
        """
        Fetches historical funding rates to calculate rolling 30-day mean, std, and Z-score.
        """
        target_symbol = self._format_symbol(symbol or self.settings.SYMBOL)
        url = f"{self.BASE_URL}/fapi/v1/fundingRate?symbol={target_symbol}&limit={limit}"

        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list):
                        df = pd.DataFrame(data)
                        df["funding_rate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
                        df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
                        return df[["timestamp", "funding_rate"]].sort_values("timestamp").reset_index(drop=True)
        except Exception as e:
            logger.warning(f"Failed to fetch funding history for {target_symbol}: {e}")

        # Fallback synthetic 30-day baseline
        timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=limit, freq="8h")
        return pd.DataFrame({"timestamp": timestamps, "funding_rate": [0.0001] * limit})

    async def fetch_open_interest(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetches current open interest amount and USD valuation.
        """
        target_symbol = self._format_symbol(symbol or self.settings.SYMBOL)
        url = f"{self.BASE_URL}/fapi/v1/openInterest?symbol={target_symbol}"

        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    oi_contracts = float(data.get("openInterest", 0.0))
                    return {
                        "symbol": target_symbol,
                        "open_interest_contracts": oi_contracts,
                        "timestamp": pd.to_datetime(data.get("time", 0), unit="ms", utc=True),
                    }
        except Exception as e:
            logger.warning(f"Failed to fetch open interest for {target_symbol}: {e}")

        return {
            "symbol": target_symbol,
            "open_interest_contracts": 50000.0,
            "timestamp": datetime.now(timezone.utc),
        }

    async def fetch_open_interest_history(
        self,
        symbol: Optional[str] = None,
        period: str = "1h",
        limit: int = 48,
    ) -> pd.DataFrame:
        """
        Fetches historical open interest series over specified period (e.g. 1h, limit=48 for 2 days).
        Used to compute 4h and 24h delta OI.
        """
        target_symbol = self._format_symbol(symbol or self.settings.SYMBOL)
        url = (
            f"{self.BASE_URL}/futures/data/openInterestHist"
            f"?symbol={target_symbol}&period={period}&limit={limit}"
        )

        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list):
                        df = pd.DataFrame(data)
                        df["sum_open_interest"] = pd.to_numeric(df["sumOpenInterest"], errors="coerce")
                        df["sum_open_interest_value"] = pd.to_numeric(df["sumOpenInterestValue"], errors="coerce")
                        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                        return df[["timestamp", "sum_open_interest", "sum_open_interest_value"]].sort_values("timestamp").reset_index(drop=True)
        except Exception as e:
            logger.warning(f"Failed to fetch historical OI for {target_symbol}: {e}")

        timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=limit, freq=period)
        return pd.DataFrame({
            "timestamp": timestamps,
            "sum_open_interest": [50000.0] * limit,
            "sum_open_interest_value": [3000000000.0] * limit,
        })

    async def fetch_top_trader_long_short_ratio(
        self,
        symbol: Optional[str] = None,
        period: str = "1h",
        limit: int = 24,
    ) -> pd.DataFrame:
        """
        Fetches Binance top trader positions Long/Short ratio.
        Ratio > 1.0 means top traders are net long; < 1.0 means net short.
        """
        target_symbol = self._format_symbol(symbol or self.settings.SYMBOL)
        url = (
            f"{self.BASE_URL}/futures/data/topLongShortPositionRatio"
            f"?symbol={target_symbol}&period={period}&limit={limit}"
        )

        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list):
                        df = pd.DataFrame(data)
                        df["long_short_ratio"] = pd.to_numeric(df["longShortRatio"], errors="coerce")
                        df["long_account"] = pd.to_numeric(df["longAccount"], errors="coerce")
                        df["short_account"] = pd.to_numeric(df["shortAccount"], errors="coerce")
                        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                        return df[["timestamp", "long_short_ratio", "long_account", "short_account"]].sort_values("timestamp").reset_index(drop=True)
        except Exception as e:
            logger.warning(f"Failed to fetch top trader L/S ratio for {target_symbol}: {e}")

        timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=limit, freq=period)
        return pd.DataFrame({
            "timestamp": timestamps,
            "long_short_ratio": [1.0] * limit,
            "long_account": [0.5] * limit,
            "short_account": [0.5] * limit,
        })
