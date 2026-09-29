"""End-to-End Historical Multi-Agent Committee Backtester (Sprint 12).

Simulates the full 9-agent autonomous committee walking forward through time
candle-by-candle with strict zero-lookahead bias, multi-timeframe synchronization,
realistic bracket execution, and institutional performance tear-sheet generation.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from loguru import logger

from core.orchestrator import OrchestratorMode, SystemOrchestrator
from core.types import AgentState, DataPacket, DataQualityReport, ExecutionMode
from engine.paper_exchange import PaperExchange
from models.portfolio_tracker import PortfolioTracker
from models.tear_sheet import TearSheetCalculator, TearSheetReport


class MultiAgentCommitteeBacktester:
    """Historical simulation engine for the StrategyOne 9-Agent Autonomous Committee."""

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        initial_equity: float = 10000.0,
        warmup_candles: int = 200,
        retrain_interval_bars: int = 96,  # 96 15m bars = 24 hours
        quiet: bool = True,
    ) -> None:
        self.symbol = symbol
        self.initial_equity = initial_equity
        self.warmup_candles = warmup_candles
        self.retrain_interval_bars = retrain_interval_bars
        self.quiet = quiet

    async def run(
        self,
        df_15m: pd.DataFrame,
        df_1h: Optional[pd.DataFrame] = None,
        df_4h: Optional[pd.DataFrame] = None,
        df_1d: Optional[pd.DataFrame] = None,
    ) -> Tuple[TearSheetReport, pd.DataFrame]:
        """
        Executes chronological historical walk-forward simulation.
        df_15m must have ['timestamp', 'open', 'high', 'low', 'close', 'volume'].
        """
        import sys
        total_bars = len(df_15m)
        if total_bars <= self.warmup_candles:
            raise ValueError(
                f"Insufficient candles ({total_bars}) for warmup period ({self.warmup_candles})."
            )

        logger.info(
            f"CommitteeBacktester: Starting simulation over {total_bars} bars "
            f"(Warmup: {self.warmup_candles} bars, Test: {total_bars - self.warmup_candles} bars)..."
        )

        # 1. Initialize dedicated backtest exchange, tracker, and orchestrator
        tracker = PortfolioTracker(initial_equity=self.initial_equity, state_file_path=None, is_backtest=True)
        exchange = PaperExchange(initial_balance_usd=self.initial_equity)

        orchestrator = SystemOrchestrator(
            mode=OrchestratorMode.BACKTEST,
            portfolio_tracker=tracker,
            exchange=exchange,
        )

        equity_series: List[float] = [self.initial_equity]
        bar_timestamps: List[datetime] = []
        active_bars_count: int = 0

        # Construct multi-timeframe lookbacks if not provided
        if df_1h is None:
            df_1h = df_15m.iloc[::4].copy().reset_index(drop=True)
        if df_4h is None:
            df_4h = df_15m.iloc[::16].copy().reset_index(drop=True)
        if df_1d is None:
            df_1d = df_15m.iloc[::96].copy().reset_index(drop=True)

        # Precompute timestamp arrays as int64 for fast warning-free binary search
        ts_1h = pd.to_datetime(df_1h["timestamp"]).astype("int64").values
        ts_4h = pd.to_datetime(df_4h["timestamp"]).astype("int64").values
        ts_1d = pd.to_datetime(df_1d["timestamp"]).astype("int64").values
        ts_15m = pd.to_datetime(df_15m["timestamp"]).astype("int64").values

        if self.quiet:
            logger.remove()
            logger.add(sys.stderr, level="WARNING")

        # 2. Chronological Walk-Forward Loop
        try:
            for i in range(self.warmup_candles, total_bars):
                current_bar = df_15m.iloc[i]
                bar_ts = current_bar["timestamp"]
                bar_close = float(current_bar["close"])
                bar_high = float(current_bar["high"])
                bar_low = float(current_bar["low"])

                # Slice history up to current candle (Strict zero look-ahead bias)
                sub_15m = df_15m.iloc[max(0, i - 800) : i + 1]

                bar_ts_int = ts_15m[i]
                idx_1h = int(np.searchsorted(ts_1h, bar_ts_int, side="right"))
                sub_1h = df_1h.iloc[max(0, idx_1h - 300) : idx_1h]

                idx_4h = int(np.searchsorted(ts_4h, bar_ts_int, side="right"))
                sub_4h = df_4h.iloc[max(0, idx_4h - 300) : idx_4h]

                idx_1d = int(np.searchsorted(ts_1d, bar_ts_int, side="right"))
                sub_1d = df_1d.iloc[max(0, idx_1d - 100) : idx_1d]

                tf_dict = {
                    "15m": sub_15m,
                    "1h": sub_1h if len(sub_1h) >= 20 else sub_15m,
                    "4h": sub_4h if len(sub_4h) >= 20 else sub_15m,
                    "1d": sub_1d if len(sub_1d) >= 10 else sub_15m,
                }

                # Build quality report
                quality = DataQualityReport(
                    status=AgentState.HEALTHY,
                    quality_scores={"15m": 1.0, "1h": 1.0, "4h": 1.0, "1d": 1.0},
                    overall_quality=1.0,
                    is_tradeable=True,
                    freshness_ok=True,
                )

                packet = DataPacket(
                    symbol=self.symbol,
                    timeframes=tf_dict,
                    features={"15m": pd.DataFrame()},
                    quality=quality,
                    latest_price=bar_close,
                    fetched_at=datetime.now(timezone.utc),
                )

                # Advance portfolio tracker calendar clock for proper daily/weekly calendar resets
                tracker.update_calendar_time(bar_ts)

                # A. Process resting bracket triggers on this candle's price action
                orchestrator.executor_agent.on_price_update(
                    symbol=self.symbol,
                    current_price=bar_close,
                    high_price=bar_high,
                    low_price=bar_low,
                )

                # B. Check GA Retraining Trigger (e.g. every 24 hours / 96 bars)
                if (i - self.warmup_candles) % self.retrain_interval_bars == 0:
                    orchestrator.last_retrain_time = None  # Force retrain

                # C. Run committee decision cycle
                await orchestrator.run_single_cycle(packet, execute_orders=True)

                # D. Track Mark-to-Market Portfolio Equity
                open_positions = [
                    p for p in orchestrator.executor_agent.bracket_manager.positions.values() if p.quantity > 0
                ]
                if open_positions:
                    active_bars_count += 1

                unrealized_pnl = sum(
                    (bar_close - p.entry_price) * p.quantity if p.side == "LONG"
                    else (p.entry_price - bar_close) * p.quantity
                    for p in open_positions
                )
                total_equity = tracker.current_cash + unrealized_pnl
                equity_series.append(total_equity)
                bar_timestamps.append(bar_ts)

                # Periodic progress logging
                if (i - self.warmup_candles) % 500 == 0 or i == total_bars - 1:
                    pct = ((i - self.warmup_candles) / max(1, total_bars - self.warmup_candles)) * 100
                    trade_cnt = len(tracker.trade_history)
                    logger.warning(
                        f"[Walk-Forward] Bar {i}/{total_bars} ({pct:.1f}%) | "
                        f"Equity: ${total_equity:,.2f} | Completed Trades: {trade_cnt}"
                    )

            # 3. Compute Tear Sheet Report
            tear_sheet = TearSheetCalculator.compute(
                equity_series=equity_series,
                trade_history=tracker.trade_history,
                initial_equity=self.initial_equity,
                active_bars=active_bars_count,
            )
            tear_sheet.trade_history = tracker.trade_history

            df_equity = pd.DataFrame({
                "timestamp": [df_15m.iloc[self.warmup_candles]["timestamp"]] + bar_timestamps,
                "equity": equity_series,
                "drawdown": tear_sheet.drawdown_curve,
            })

            logger.warning(
                f"CommitteeBacktester: Simulation completed. Return: {tear_sheet.total_return_pct:+.2%} | "
                f"Sharpe: {tear_sheet.annualized_sharpe:.2f} | Max DD: {tear_sheet.max_drawdown_pct:.2%} | "
                f"Trades: {tear_sheet.total_trades} (Win Rate: {tear_sheet.win_rate_pct:.1%})"
            )

            await orchestrator.shutdown()
            return tear_sheet, df_equity
        finally:
            if self.quiet:
                logger.remove()
                logger.add(sys.stderr, level="INFO")
