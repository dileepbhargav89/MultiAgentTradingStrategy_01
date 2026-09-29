"""Institutional Performance Tear-Sheet & Quantitative Risk Analytics (Sprint 12).

Calculates comprehensive risk-adjusted performance metrics, return distributions,
underwater drawdown profiles, and trade efficiency statistics for the StrategyOne
multi-agent autonomous committee.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


@dataclass
class TearSheetReport:
    """Consolidated institutional performance tear-sheet report."""
    initial_equity: float
    final_equity: float
    total_return_usd: float
    total_return_pct: float
    cagr_pct: float
    annualized_sharpe: float
    annualized_sortino: float
    calmar_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration_bars: int
    profit_factor: float
    win_rate_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_trade_pnl_usd: float
    avg_win_usd: float
    avg_loss_usd: float
    payoff_ratio: float
    total_fees_paid_usd: float
    exposure_time_pct: float
    equity_curve: List[float] = field(default_factory=list)
    drawdown_curve: List[float] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Serializes tear-sheet report to dictionary."""
        return {
            "initial_equity": round(self.initial_equity, 2),
            "final_equity": round(self.final_equity, 2),
            "total_return_usd": round(self.total_return_usd, 2),
            "total_return_pct": round(self.total_return_pct, 4),
            "cagr_pct": round(self.cagr_pct, 4),
            "annualized_sharpe": round(self.annualized_sharpe, 2),
            "annualized_sortino": round(self.annualized_sortino, 2),
            "calmar_ratio": round(self.calmar_ratio, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "max_drawdown_duration_bars": self.max_drawdown_duration_bars,
            "profit_factor": round(self.profit_factor, 2),
            "win_rate_pct": round(self.win_rate_pct, 4),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_trade_pnl_usd": round(self.avg_trade_pnl_usd, 2),
            "avg_win_usd": round(self.avg_win_usd, 2),
            "avg_loss_usd": round(self.avg_loss_usd, 2),
            "payoff_ratio": round(self.payoff_ratio, 2),
            "total_fees_paid_usd": round(self.total_fees_paid_usd, 2),
            "exposure_time_pct": round(self.exposure_time_pct, 4),
            "timestamp": self.timestamp.isoformat(),
        }


class TearSheetCalculator:
    """Computes quantitative metrics from equity curves and closed trade logs."""

    @staticmethod
    def compute(
        equity_series: List[float],
        trade_history: List[Dict[str, Any]],
        initial_equity: float = 10000.0,
        periods_per_year: int = 35040,  # 15-minute bars per year (365 * 24 * 4)
        active_bars: int = 0,
    ) -> TearSheetReport:
        """Computes comprehensive quantitative performance tear-sheet."""
        if not equity_series:
            equity_series = [initial_equity]

        equities = np.array(equity_series, dtype=float)
        final_equity = float(equities[-1])
        total_pnl_usd = final_equity - initial_equity
        total_return_pct = total_pnl_usd / initial_equity if initial_equity > 0 else 0.0

        # Bar returns
        returns = np.diff(equities) / equities[:-1]
        returns = returns[np.isfinite(returns)]

        # Annualized Sharpe
        if len(returns) > 1 and np.std(returns) > 1e-8:
            sharpe = float((np.mean(returns) / np.std(returns)) * np.sqrt(periods_per_year))
        else:
            sharpe = 0.0

        # Annualized Sortino
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 1 and np.std(downside_returns) > 1e-8:
            downside_std = float(np.std(downside_returns))
            sortino = float((np.mean(returns) / downside_std) * np.sqrt(periods_per_year))
        else:
            sortino = sharpe if sharpe > 0 else 0.0

        # High Water Mark & Drawdown profile
        hwm = np.maximum.accumulate(equities)
        drawdowns = (hwm - equities) / hwm
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Max drawdown duration
        max_dd_duration = 0
        current_dd_duration = 0
        for dd in drawdowns:
            if dd > 1e-5:
                current_dd_duration += 1
                if current_dd_duration > max_dd_duration:
                    max_dd_duration = current_dd_duration
            else:
                current_dd_duration = 0

        # Calmar Ratio
        years = len(equities) / periods_per_year if periods_per_year > 0 else 1.0
        cagr = (final_equity / initial_equity) ** (1.0 / max(years, 0.001)) - 1.0 if (years > 0 and final_equity > 0) else 0.0
        calmar = cagr / max_dd if max_dd > 1e-6 else 0.0

        # Trade metrics
        pnls = [float(t.get("realized_pnl_usd", t.get("net_pnl", t.get("gross_pnl", 0.0)))) for t in trade_history]
        fees = [float(t.get("fee_paid_usd", t.get("fees", 0.0))) for t in trade_history]
        total_fees = float(sum(fees))
        total_trades = len(pnls)

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 1e-6 else (99.0 if gross_profit > 0 else 0.0)

        avg_pnl = float(np.mean(pnls)) if pnls else 0.0
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(abs(np.mean(losses))) if losses else 0.0
        payoff_ratio = (avg_win / avg_loss) if avg_loss > 1e-6 else (avg_win if avg_win > 0 else 0.0)

        exposure_pct = float(active_bars / len(equities)) if len(equities) > 0 else 0.0

        return TearSheetReport(
            initial_equity=initial_equity,
            final_equity=final_equity,
            total_return_usd=total_pnl_usd,
            total_return_pct=total_return_pct,
            cagr_pct=cagr,
            annualized_sharpe=sharpe,
            annualized_sortino=sortino,
            calmar_ratio=calmar,
            max_drawdown_pct=max_dd,
            max_drawdown_duration_bars=max_dd_duration,
            profit_factor=profit_factor,
            win_rate_pct=win_rate,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_trade_pnl_usd=avg_pnl,
            avg_win_usd=avg_win,
            avg_loss_usd=avg_loss,
            payoff_ratio=payoff_ratio,
            total_fees_paid_usd=total_fees,
            exposure_time_pct=exposure_pct,
            equity_curve=equities.tolist(),
            drawdown_curve=drawdowns.tolist(),
        )
