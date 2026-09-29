"""StrategyOne: Unified CLI Entrypoint and Production Daemon Runtime.

Boots the autonomous multi-agent committee, runs the live timing scheduler loop,
subscribes to Binance WebSocket real-time streams, and optionally launches the
interactive Streamlit monitoring dashboard.
"""

import argparse
import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional
from loguru import logger

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.events import EVENT_CANDLE_CLOSED, EVENT_MARKET_TICK, event_bus
from core.orchestrator import OrchestratorMode, SystemOrchestrator
from core.types import DataPacket, ExecutionMode
from data.fetcher import DataFetcher
from data.websocket_client import BinanceWebSocketClient


class StrategyOneRuntime:
    """Manages system lifecycles, background tasks, and daemon loops."""

    def __init__(
        self,
        mode: str = "paper",
        symbol: str = "BTC/USDT",
        checkpoint_path: Optional[str] = None,
        enable_ws: bool = True,
        launch_dashboard: bool = False,
    ) -> None:
        self.mode_str = mode.lower()
        self.symbol = symbol
        self.checkpoint_path = checkpoint_path
        self.enable_ws = enable_ws
        self.launch_dashboard = launch_dashboard

        # Map execution mode
        if self.mode_str == "live":
            self.orch_mode = OrchestratorMode.LIVE_DAEMON
            self.is_testnet = False
        elif self.mode_str == "testnet":
            self.orch_mode = OrchestratorMode.LIVE_DAEMON
            self.is_testnet = True
        else:
            self.orch_mode = OrchestratorMode.PAPER_DAEMON
            self.is_testnet = True

        self.orchestrator: Optional[SystemOrchestrator] = None
        self.ws_client: Optional[BinanceWebSocketClient] = None
        self.dashboard_process: Optional[subprocess.Popen] = None
        self.fetcher = DataFetcher()
        self.is_running = False

    async def initialize(self) -> None:
        """Initializes orchestrator, state recovery, and dashboard if requested."""
        logger.info(f"StrategyOneRuntime: Booting runtime in {self.orch_mode.value} mode for {self.symbol}...")

        self.orchestrator = SystemOrchestrator(
            mode=self.orch_mode,
            checkpoint_path=self.checkpoint_path,
        )

        # Attempt state recovery from checkpoint
        recovered = self.orchestrator.recover_state()
        if recovered:
            logger.info(
                f"StrategyOneRuntime: Checkpoint restored. Resuming at Cycle #{self.orchestrator.cycle_count}."
            )
        else:
            logger.info("StrategyOneRuntime: Starting fresh state session (zero prior active positions).")

        # Launch Streamlit dashboard subprocess if requested
        if self.launch_dashboard:
            self._start_dashboard()

        # Wire WebSocket tick handler to TradeExecutionAgent
        if self.enable_ws:
            self.ws_client = BinanceWebSocketClient(
                symbol=self.symbol,
                timeframe="15m",
                testnet=self.is_testnet,
                on_tick=self._on_live_tick,
            )

    def _on_live_tick(self, tick_data: dict) -> None:
        """Dispatches sub-second live tick to executor agent for bracket evaluation."""
        if self.orchestrator:
            price = tick_data.get("price", 0.0)
            if price > 0.0:
                self.orchestrator.executor_agent.on_price_update(
                    symbol=self.symbol,
                    current_price=price,
                    high_price=tick_data.get("ask", price),
                    low_price=tick_data.get("bid", price),
                )

    def _start_dashboard(self) -> None:
        """Launches the Streamlit dashboard as an independent sub-process."""
        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "dashboard/app.py",
            "--server.port=8501",
            "--server.headless=true",
        ]
        logger.info("StrategyOneRuntime: Spawning Streamlit dashboard on http://localhost:8501 ...")
        try:
            self.dashboard_process = subprocess.Popen(cmd)
        except Exception as e:
            logger.error(f"StrategyOneRuntime: Failed to start dashboard subprocess: {e}")

    async def run(self, single_cycle_only: bool = False) -> None:
        """Runs the main runtime execution loop."""
        self.is_running = True

        if self.ws_client:
            await self.ws_client.start()

        logger.info("StrategyOneRuntime: Master loop operational. Waiting for candle boundaries / ticks.")

        if single_cycle_only:
            logger.info("StrategyOneRuntime: --single-cycle flag set. Fetching data and running 1 cycle.")
            await self.orchestrator.dq_agent.evaluate_live(self.symbol)
            packet = self.orchestrator.dq_agent.build_data_packet(self.symbol)
            if packet:
                res = await self.orchestrator.run_single_cycle(packet)
                logger.info(f"StrategyOneRuntime: Single cycle finished: {res.get('status')}")
            else:
                logger.warning("StrategyOneRuntime: Could not build DataPacket from live evaluation.")
            await self.shutdown()
            return

        # Main daemon loop
        try:
            while self.is_running:
                # 1. Check if candle close is due
                seconds_to_close = self.orchestrator.scheduler.get_seconds_until_next_candle("15m")
                if seconds_to_close <= 1.0:
                    logger.info("StrategyOneRuntime: 15m candle boundary reached. Running decision cycle...")
                    try:
                        await self.orchestrator.dq_agent.evaluate_live(self.symbol)
                        packet = self.orchestrator.dq_agent.build_data_packet(self.symbol)
                        if packet:
                            await self.orchestrator.run_single_cycle(packet)
                    except Exception as e:
                        logger.error(f"StrategyOneRuntime: Error executing decision cycle: {e}")

                    # Sleep past candle boundary
                    await asyncio.sleep(2.0)
                else:
                    # Tick monitoring sleep
                    await asyncio.sleep(self.orchestrator.scheduler.tick_interval_sec)

        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Clean shutdown handler."""
        logger.info("StrategyOneRuntime: Initiating graceful system shutdown...")
        self.is_running = False

        if self.ws_client:
            await self.ws_client.stop()

        if self.orchestrator:
            await self.orchestrator.shutdown()

        if self.dashboard_process and self.dashboard_process.poll() is None:
            logger.info("StrategyOneRuntime: Terminating Streamlit dashboard subprocess...")
            self.dashboard_process.terminate()
            try:
                self.dashboard_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.dashboard_process.kill()

        logger.info("StrategyOneRuntime: Shutdown complete. All services halted cleanly.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StrategyOne Autonomous Crypto Trading System")
    parser.add_argument(
        "--mode",
        choices=["paper", "testnet", "live"],
        default="paper",
        help="Execution target environment (default: paper)",
    )
    parser.add_argument(
        "--symbol",
        default="BTC/USDT",
        help="Target trading pair symbol (default: BTC/USDT)",
    )
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="Path to custom state checkpoint file",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Launch interactive Streamlit monitoring dashboard",
    )
    parser.add_argument(
        "--no-ws",
        action="store_true",
        help="Disable Binance WebSocket live stream (fallback to polling)",
    )
    parser.add_argument(
        "--single-cycle",
        action="store_true",
        help="Execute a single decision cycle and exit",
    )
    return parser.parse_args()


async def main_async() -> None:
    args = parse_args()
    runtime = StrategyOneRuntime(
        mode=args.mode,
        symbol=args.symbol,
        checkpoint_path=args.checkpoint,
        enable_ws=not args.no_ws,
        launch_dashboard=args.dashboard,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(runtime.shutdown()))
        except NotImplementedError:
            pass  # Windows signals handled via KeyboardInterrupt

    await runtime.initialize()
    await runtime.run(single_cycle_only=args.single_cycle)


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("StrategyOne: Process interrupted by user. Exiting.")


if __name__ == "__main__":
    main()
