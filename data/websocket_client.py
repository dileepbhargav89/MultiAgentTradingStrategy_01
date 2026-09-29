"""High-Frequency Binance WebSocket Live Streaming Gateway.

Provides real-time sub-second bookTicker and kline bar streaming for StrategyOne.
Maintains resilient auto-reconnect with exponential backoff, ping/pong heartbeats,
and dispatches events directly to the system EventBus and BracketOrderManager.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
from loguru import logger
import websockets

from core.events import EVENT_CANDLE_CLOSED, EVENT_MARKET_TICK, event_bus


class BinanceWebSocketClient:
    """Async WebSocket streaming gateway for real-time market data ingestion."""

    LIVE_BASE_URL = "wss://stream.binance.com:9443/stream"
    TESTNET_BASE_URL = "wss://stream.binance.vision:9443/stream"

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        testnet: bool = False,
        on_tick: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_candle: Optional[Callable[[Dict[str, Any]], None]] = None,
        max_reconnect_attempts: int = 10,
        custom_stream_url: Optional[str] = None,
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.testnet = testnet
        self.on_tick = on_tick
        self.on_candle = on_candle
        self.max_reconnect_attempts = max_reconnect_attempts
        self.custom_stream_url = custom_stream_url

        # Stream identifier formatting: BTC/USDT -> btcusdt
        self.raw_symbol = symbol.replace("/", "").lower()
        self.stream_query = f"{self.raw_symbol}@bookTicker/{self.raw_symbol}@kline_{timeframe}"

        # State tracking
        self.is_running = False
        self.is_connected = False
        self.reconnect_count = 0
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 30.0

        # Latest cache
        self.latest_tick: Optional[Dict[str, Any]] = None
        self.latest_kline: Optional[Dict[str, Any]] = None

        # Background task handle
        self._worker_task: Optional[asyncio.Task] = None

    @property
    def url(self) -> str:
        """Constructs the combined stream WebSocket URL."""
        if self.custom_stream_url:
            return self.custom_stream_url
        base = self.TESTNET_BASE_URL if self.testnet else self.LIVE_BASE_URL
        return f"{base}?streams={self.stream_query}"

    async def start(self) -> None:
        """Starts the WebSocket listener loop in the background."""
        if self.is_running:
            logger.warning("BinanceWebSocketClient is already running.")
            return

        self.is_running = True
        logger.info(f"BinanceWebSocketClient: Starting live stream for {self.symbol} -> {self.url}")
        self._worker_task = asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        """Terminates the WebSocket connection cleanly."""
        logger.info("BinanceWebSocketClient: Stopping stream...")
        self.is_running = False
        self.is_connected = False

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("BinanceWebSocketClient: Stream stopped gracefully.")

    async def _listen_loop(self) -> None:
        """Internal resilient connection and message listening loop."""
        while self.is_running:
            try:
                logger.info(f"BinanceWebSocketClient: Connecting to {self.url}...")
                async with websockets.connect(
                    self.url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self.is_connected = True
                    self.reconnect_count = 0
                    self._reconnect_delay = 1.0
                    logger.info(f"BinanceWebSocketClient: Connected successfully to {self.symbol} stream.")

                    while self.is_running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                            self._handle_message(msg)
                        except asyncio.TimeoutError:
                            # Ping-pong will maintain connection; timeout triggers health check
                            logger.debug("BinanceWebSocketClient: Stream idle for 30s, verifying connection...")
                            pong = await ws.ping()
                            await asyncio.wait_for(pong, timeout=5.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.is_connected = False
                self.reconnect_count += 1
                logger.warning(
                    f"BinanceWebSocketClient: Connection dropped ({e}). "
                    f"Attempting reconnect #{self.reconnect_count} in {self._reconnect_delay:.1f}s..."
                )
                if not self.is_running:
                    break

                if self.reconnect_count > self.max_reconnect_attempts:
                    logger.error(
                        f"BinanceWebSocketClient: Exceeded max reconnect attempts ({self.max_reconnect_attempts}). Stopping."
                    )
                    self.is_running = False
                    break

                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2.0, self._max_reconnect_delay)

    def _handle_message(self, raw_message: str) -> None:
        """Parses combined stream messages and dispatches events."""
        try:
            msg = json.loads(raw_message)
            stream_name = msg.get("stream", "")
            data = msg.get("data", {})

            # 1. Best Bid/Ask Book Ticker stream
            if "bookTicker" in stream_name:
                bid = float(data.get("b", 0.0))
                ask = float(data.get("a", 0.0))
                mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else float(data.get("c", 0.0))

                tick_payload = {
                    "symbol": self.symbol,
                    "bid": bid,
                    "ask": ask,
                    "price": mid,
                    "timestamp": datetime.now(timezone.utc),
                }
                self.latest_tick = tick_payload
                event_bus.publish(EVENT_MARKET_TICK, tick_payload)

                if self.on_tick:
                    self.on_tick(tick_payload)

            # 2. Kline / Candlestick stream
            elif "kline" in stream_name:
                k = data.get("k", {})
                is_closed = bool(k.get("x", False))

                kline_payload = {
                    "symbol": self.symbol,
                    "timeframe": k.get("i", self.timeframe),
                    "open": float(k.get("o", 0.0)),
                    "high": float(k.get("h", 0.0)),
                    "low": float(k.get("l", 0.0)),
                    "close": float(k.get("c", 0.0)),
                    "volume": float(k.get("v", 0.0)),
                    "is_closed": is_closed,
                    "timestamp": datetime.now(timezone.utc),
                }
                self.latest_kline = kline_payload

                if is_closed:
                    logger.info(
                        f"BinanceWebSocketClient: {self.symbol} {self.timeframe} Candle Bar Closed @ ${kline_payload['close']:,.2f}"
                    )
                    event_bus.publish(EVENT_CANDLE_CLOSED, kline_payload)
                    if self.on_candle:
                        self.on_candle(kline_payload)

        except Exception as e:
            logger.error(f"BinanceWebSocketClient: Error parsing message: {e}")
