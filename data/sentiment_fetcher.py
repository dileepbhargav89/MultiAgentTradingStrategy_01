"""Macro sentiment fetcher: Alternative.me Fear & Greed Index with in-memory caching and fallback."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import aiohttp
from loguru import logger


class SentimentFetcher:
    """
    Fetches the crypto market Fear & Greed Index from the free Alternative.me API.
    Updates once daily, so responses are cached in memory for 1 hour.
    Gracefully falls back to neutral (50) on network failures.
    """

    API_URL = "https://api.alternative.me/fng/?limit=30"

    def __init__(self, cache_ttl_seconds: int = 3600) -> None:
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cached_data: Optional[Dict[str, Any]] = None
        self._last_fetch_time: Optional[datetime] = None

    async def fetch_fear_and_greed(self) -> Dict[str, Any]:
        """
        Fetches Fear & Greed Index (0 to 100).
        0-24: Extreme Fear
        25-44: Fear
        45-55: Neutral
        56-75: Greed
        76-100: Extreme Greed
        """
        now = datetime.now(timezone.utc)
        if (
            self._cached_data is not None
            and self._last_fetch_time is not None
            and (now - self._last_fetch_time) < self.cache_ttl
        ):
            return {**self._cached_data, "is_cached": True}

        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.API_URL) as response:
                    if response.status == 200:
                        json_resp = await response.json()
                        data_list = json_resp.get("data", [])
                        if data_list:
                            latest = data_list[0]
                            val = int(latest.get("value", 50))
                            classification = str(latest.get("value_classification", "Neutral"))

                            self._cached_data = {
                                "value": val,
                                "classification": classification,
                                "timestamp": now,
                            }
                            self._last_fetch_time = now
                            return {**self._cached_data, "is_cached": False}
        except Exception as e:
            logger.warning(f"Failed to fetch Fear & Greed Index from Alternative.me: {e}")

        # If cache exists (even if stale), return it
        if self._cached_data is not None:
            return {**self._cached_data, "is_cached": True}

        # Safe fallback
        return {
            "value": 50,
            "classification": "Neutral",
            "timestamp": now,
            "is_cached": False,
        }
