"""Ultra-fast vectorized backtesting engine with realistic fees, slippage, and zero look-ahead bias."""

import math
from typing import Optional, Tuple
import numpy as np
import pandas as pd

from core.types import BacktestResult, StrategyGenome
from engine.species_strategies import SpeciesStrategyBuilder


class VectorizedBacktester:
    """
    Simulates trading strategies across thousands of historical candles in milliseconds.
    Strictly enforces zero look-ahead bias by shifting signals (P_t = S_{t-1}).
    Applies realistic Binance VIP0/Retail fees (0.04% taker) and market slippage (0.01%).
    """

    def __init__(
        self,
        taker_fee_pct: float = 0.0004,   # 0.04% taker fee
        slippage_pct: float = 0.0001,    # 0.01% market impact / slippage
        annualization_factor: float = 8760.0, # 1-hour candles per year (24 * 365)
    ) -> None:
        self.taker_fee_pct = taker_fee_pct
        self.slippage_pct = slippage_pct
        self.annualization_factor = annualization_factor
        self.total_cost_per_trade = taker_fee_pct + slippage_pct

    def backtest(
        self,
        df: pd.DataFrame,
        genome: StrategyGenome,
        initial_capital: float = 10000.0,
    ) -> BacktestResult:
        """
        Executes a vectorized backtest for a given genome on historical price data.
        Returns a BacktestResult with complete performance and risk analytics.
        """
        if len(df) < 50:
            return self._empty_result(genome)

        # 1. Generate Raw Signals in {-1, 0, 1}
        signals = SpeciesStrategyBuilder.generate_signals(df, genome)

        # 2. Strict Zero Look-Ahead Shift: Position_t = Signal_{t-1}
        positions = np.roll(signals, 1)
        positions[0] = 0.0  # Cannot hold position on the first bar

        # 3. Vectorized Log Returns
        c = df["close"].values
        # Safe log return calculation avoiding log(0) or negative price artifacts
        prev_c = np.roll(c, 1)
        prev_c[0] = c[0]
        log_returns = np.zeros(len(c), dtype=float)
        valid_mask = (c > 0) & (prev_c > 0)
        log_returns[valid_mask] = np.log(c[valid_mask] / prev_c[valid_mask])
        log_returns[0] = 0.0

        # 4. Position Transitions & Friction
        pos_changes = np.abs(positions - np.roll(positions, 1))
        pos_changes[0] = np.abs(positions[0])
        trade_costs = pos_changes * self.total_cost_per_trade

        # 5. Net Strategy Returns
        strategy_returns = (positions * log_returns) - trade_costs

        # 6. Cumulative Equity Curve
        cum_returns = np.cumsum(strategy_returns)
        equity = initial_capital * np.exp(cum_returns)

        # 7. Drawdown Series
        running_max = np.maximum.accumulate(equity)
        drawdown_series = (running_max - equity) / np.maximum(running_max, 1e-8)
        max_drawdown = float(np.max(drawdown_series))

        # 8. Trade Metrics & Count
        # Count non-zero position entries
        total_trades = int(np.sum(pos_changes > 0.5))
        net_pnl_pct = float((equity[-1] / initial_capital - 1.0) * 100.0)
        total_return_ratio = float(equity[-1] / initial_capital)

        # 9. Risk-Adjusted Ratios (Sharpe, Sortino, Calmar)
        mean_r = float(np.mean(strategy_returns))
        std_r = float(np.std(strategy_returns))

        sqrt_ann = math.sqrt(self.annualization_factor)
        ann_mean = mean_r * self.annualization_factor
        ann_vol = std_r * sqrt_ann

        sharpe = (ann_mean / ann_vol) if ann_vol > 1e-6 else 0.0
        sharpe = float(np.clip(sharpe, -10.0, 10.0))

        # Downside deviation for Sortino
        negative_returns = strategy_returns[strategy_returns < 0]
        downside_std = float(np.std(negative_returns)) if len(negative_returns) > 2 else 1e-4
        sortino = (ann_mean / (downside_std * sqrt_ann)) if downside_std > 1e-6 else 0.0
        sortino = float(np.clip(sortino, -10.0, 15.0))

        # Calmar Ratio = Annualized Return / Max Drawdown
        calmar = (ann_mean / max_drawdown) if max_drawdown > 0.005 else (ann_mean / 0.005)
        calmar = float(np.clip(calmar, -10.0, 20.0))

        # Win Rate on active bars
        active_bars = strategy_returns[positions != 0]
        if len(active_bars) > 0:
            win_rate = float(np.sum(active_bars > 0) / len(active_bars))
        else:
            win_rate = 0.0

        # Profit Factor
        gross_profits = float(np.sum(strategy_returns[strategy_returns > 0]))
        gross_losses = float(np.abs(np.sum(strategy_returns[strategy_returns < 0])))
        profit_factor = (gross_profits / gross_losses) if gross_losses > 1e-6 else (2.0 if gross_profits > 0 else 0.0)
        profit_factor = float(np.clip(profit_factor, 0.0, 10.0))

        # 10. Composite Fitness Score (Multi-Objective Optimization)
        # Penalize if trade count is too low (< 5 trades is statistically meaningless)
        trade_penalty = 1.0 if total_trades >= 10 else (total_trades / 10.0)
        # Heavy penalty on catastrophic drawdown (> 20%)
        mdd_penalty = max(0.0, 1.0 - (max_drawdown / 0.25))

        fitness = (0.40 * max(0.0, sharpe) + 0.30 * min(profit_factor, 3.0) + 0.30 * max(0.0, calmar * 0.2)) * trade_penalty * mdd_penalty
        fitness = float(round(fitness, 4))

        # Sample equity curve down to max 100 points for memory efficiency
        step = max(1, len(equity) // 100)
        sampled_equity = [round(float(x), 2) for x in equity[::step]]

        return BacktestResult(
            strategy_id=genome.strategy_id,
            species=genome.species,
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            calmar_ratio=round(calmar, 2),
            profit_factor=round(profit_factor, 2),
            max_drawdown=round(max_drawdown, 4),
            win_rate=round(win_rate, 4),
            total_trades=total_trades,
            net_pnl_pct=round(net_pnl_pct, 2),
            total_return=round(total_return_ratio, 4),
            equity_curve=sampled_equity,
            strategy_returns=strategy_returns,
            fitness_score=fitness,
        )

    def _empty_result(self, genome: StrategyGenome) -> BacktestResult:
        return BacktestResult(
            strategy_id=genome.strategy_id,
            species=genome.species,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            total_trades=0,
            net_pnl_pct=0.0,
            total_return=1.0,
            equity_curve=[10000.0],
            strategy_returns=None,
            fitness_score=0.0,
        )
