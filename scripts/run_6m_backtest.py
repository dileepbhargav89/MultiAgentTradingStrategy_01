"""Full 6-Month Historical Backtesting and Tear-Sheet Engine for StrategyOne.

Runs:
1. Multi-species vectorized benchmarking across 6 months of BTC/USDT data.
2. Full 9-Agent Autonomous Committee walk-forward simulation.
3. Institutional tear-sheet generation (Risk, Return, Monthly breakdowns, VaR/CVaR, Regimes).
Saves equity curves and metrics for UI dashboard visualization.
"""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from loguru import logger
import warnings
warnings.filterwarnings("ignore")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.types import StrategyGenome, StrategySpecies, VolatilityRegime
from engine.species_strategies import SpeciesStrategyBuilder
from engine.vectorized_backtester import VectorizedBacktester
from engine.committee_backtester import MultiAgentCommitteeBacktester
from models.tear_sheet import TearSheetCalculator, TearSheetReport
from models.var_calculator import VaRCalculator


CACHE_DIR = PROJECT_ROOT / "data" / "cache"
OUTPUT_DIR = PROJECT_ROOT / "data"


def load_6m_data():
    """Loads 6-month cached data for 15m, 1h, 4h, and 1d timeframes."""
    file_15m = CACHE_DIR / "BTCUSDT_180d_15m.csv"
    file_1h = CACHE_DIR / "BTCUSDT_180d_1h.csv"
    file_4h = CACHE_DIR / "BTCUSDT_180d_4h.csv"
    file_1d = CACHE_DIR / "BTCUSDT_180d_1d.csv"

    if not file_15m.exists():
        raise FileNotFoundError(f"Missing {file_15m}. Run download_6m_data.py first.")

    df_15m = pd.read_csv(file_15m)
    df_1h = pd.read_csv(file_1h) if file_1h.exists() else df_15m.iloc[::4].copy()
    df_4h = pd.read_csv(file_4h) if file_4h.exists() else df_15m.iloc[::16].copy()
    df_1d = pd.read_csv(file_1d) if file_1d.exists() else df_15m.iloc[::96].copy()

    for df in [df_15m, df_1h, df_4h, df_1d]:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

    return df_15m, df_1h, df_4h, df_1d


def run_vectorized_species_benchmarks(df_1h: pd.DataFrame, initial_capital: float = 10000.0) -> dict:
    """Runs vectorized backtests for all 4 strategy species across the 6-month 1h dataset."""
    logger.info("Running Vectorized Multi-Species Benchmarks over 6 months...")
    vb = VectorizedBacktester()

    species_list = [
        (StrategySpecies.MOMENTUM_TREND, "Momentum Trend Following"),
        (StrategySpecies.MEAN_REVERSION, "Mean Reversion / BB Fade"),
        (StrategySpecies.BREAKOUT_VOLATILITY, "Volatility Breakout"),
        (StrategySpecies.REGIME_ADAPTIVE, "Regime Adaptive Hybrid"),
    ]

    results = {}
    for spec, name in species_list:
        genome = StrategyGenome(strategy_id=f"GEN-{spec.name[:3]}", species=spec)
        res = vb.backtest(df_1h, genome, initial_capital=initial_capital)
        results[spec.name] = {
            "name": name,
            "species": spec.name,
            "total_return_pct": round(res.net_pnl_pct, 2),
            "annualized_sharpe": round(res.sharpe_ratio, 2),
            "sortino_ratio": round(res.sortino_ratio, 2),
            "max_drawdown_pct": round(res.max_drawdown * 100.0, 2),
            "calmar_ratio": round(res.calmar_ratio, 2),
            "win_rate_pct": round(res.win_rate * 100.0, 1),
            "profit_factor": round(res.profit_factor, 2),
            "total_trades": res.total_trades,
        }
        logger.info(
            f"  {name:26} | Return: {results[spec.name]['total_return_pct']:+6.2f}% | "
            f"Sharpe: {results[spec.name]['annualized_sharpe']:5.2f} | "
            f"MaxDD: {results[spec.name]['max_drawdown_pct']:5.2f}% | "
            f"Trades: {results[spec.name]['total_trades']:4d} | "
            f"WinRate: {results[spec.name]['win_rate_pct']:4.1f}%"
        )
    return results


async def run_committee_6m_backtest(
    df_15m: pd.DataFrame,
    df_1h: pd.DataFrame,
    df_4h: pd.DataFrame,
    df_1d: pd.DataFrame,
    initial_equity: float = 10000.0,
    stride: int = 1,
) -> tuple:
    """
    Executes the full 9-agent autonomous committee walk-forward backtest.
    To cover the full 6 months with institutional precision:
    - Warmup: 300 bars
    - Uses 15m primary candles with synchronized 1h/4h/1d MTF context
    - Stride can step bars for ultra-fast simulation if needed, default 1 bar = every 15m.
    """
    logger.info(f"Running Full 9-Agent Committee Backtest over {len(df_15m)} 15m bars (~180 days, stride={stride})...")
    
    # Mute cycle INFO logging during walk-forward loop to prevent console I/O bottlenecks
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    backtester = MultiAgentCommitteeBacktester(
        symbol="BTC/USDT",
        initial_equity=initial_equity,
        warmup_candles=150,
        retrain_interval_bars=48,  # Retrain every 48 bars (~4 days at 2h stride)
    )

    tear_sheet, df_equity = await backtester.run(
        df_15m=df_15m if stride == 1 else df_15m.iloc[::stride].copy().reset_index(drop=True),
        df_1h=df_1h,
        df_4h=df_4h,
        df_1d=df_1d,
    )

    # Restore INFO logging
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    return tear_sheet, df_equity


def compute_monthly_breakdown(df_equity: pd.DataFrame) -> list:
    """Computes month-by-month return and drawdown table."""
    df = df_equity.copy()
    df["year_month"] = df["timestamp"].dt.to_period("M")
    
    monthly_stats = []
    for ym, group in df.groupby("year_month"):
        start_eq = group["equity"].iloc[0]
        end_eq = group["equity"].iloc[-1]
        ret_pct = ((end_eq - start_eq) / start_eq) * 100.0
        max_dd = group["drawdown"].min()
        monthly_stats.append({
            "month": str(ym),
            "start_equity": round(float(start_eq), 2),
            "end_equity": round(float(end_eq), 2),
            "return_pct": round(float(ret_pct), 2),
            "max_drawdown_pct": round(float(max_dd), 2),
        })
    return monthly_stats


def compute_regime_analytics(df_1h: pd.DataFrame) -> dict:
    """Classifies regimes across the 6-month period and computes market distribution."""
    # Compute 20-period ATR and 50-period SMA slope
    df = df_1h.copy()
    df["sma50"] = df["close"].rolling(50).mean()
    df["sma200"] = df["close"].rolling(200).mean()
    df["ret"] = df["close"].pct_change()
    df["rolling_vol"] = df["ret"].rolling(24).std() * np.sqrt(24 * 365)

    regimes = {
        "BULL_TREND": int(((df["close"] > df["sma50"]) & (df["sma50"] > df["sma200"])).sum()),
        "BEAR_TREND": int(((df["close"] < df["sma50"]) & (df["sma50"] < df["sma200"])).sum()),
        "CHOPPY_MEAN_REVERT": int((df["rolling_vol"] < df["rolling_vol"].median()).sum()),
        "HIGH_VOL_CHAOS": int((df["rolling_vol"] > df["rolling_vol"].quantile(0.85)).sum()),
    }
    total = sum(regimes.values())
    pcts = {k: round(v / total * 100.0, 1) for k, v in regimes.items()}
    return pcts


async def main():
    logger.info("=================================================================")
    logger.info("   STRATEGYONE 6-MONTH BTC/USDT MULTI-AGENT BACKTEST BENCHMARK   ")
    logger.info("=================================================================")

    df_15m, df_1h, df_4h, df_1d = load_6m_data()

    btc_start_price = float(df_15m["close"].iloc[0])
    btc_end_price = float(df_15m["close"].iloc[-1])
    btc_return_pct = ((btc_end_price - btc_start_price) / btc_start_price) * 100.0

    logger.info(f"Test Period: {df_15m['timestamp'].iloc[0]} -> {df_15m['timestamp'].iloc[-1]} (180 Days)")
    logger.info(f"BTC Start: ${btc_start_price:,.2f} | BTC End: ${btc_end_price:,.2f} | Buy & Hold: {btc_return_pct:+.2f}%")
    logger.info("-----------------------------------------------------------------")

    # 1. Multi-Species Vectorized Benchmark
    species_results = run_vectorized_species_benchmarks(df_1h, initial_capital=10000.0)

    # 2. Committee Multi-Agent Backtest
    # To run across 180 days cleanly, sample at 2-hour intervals (stride 8 on 15m):
    # 2,185 steps executes all 9 agents with high speed and zero-lookahead bias.
    stride = 8
    tear_sheet, df_equity = await run_committee_6m_backtest(
        df_15m=df_15m,
        df_1h=df_1h,
        df_4h=df_4h,
        df_1d=df_1d,
        initial_equity=10000.0,
        stride=stride,
    )

    # 3. Monthly Breakdown
    monthly_stats = compute_monthly_breakdown(df_equity)

    # 4. Regime Distribution
    regime_dist = compute_regime_analytics(df_1h)

    # 5. VaR Risk Analytics on Equity Curve
    equity_returns = df_equity["equity"].pct_change().dropna().values
    var_summary = VaRCalculator.compute_risk_summary(
        equity_returns,
        portfolio_equity=float(df_equity["equity"].iloc[-1]),
        timeframe="1h",
    )

    # Final Consolidated Output
    final_output = {
        "metadata": {
            "symbol": "BTC/USDT",
            "start_time": str(df_15m["timestamp"].iloc[0]),
            "end_time": str(df_15m["timestamp"].iloc[-1]),
            "duration_days": 180,
            "btc_start_price": btc_start_price,
            "btc_end_price": btc_end_price,
            "btc_buy_and_hold_pct": round(btc_return_pct, 2),
            "initial_equity": 10000.0,
            "final_equity": round(float(df_equity["equity"].iloc[-1]), 2),
            "total_pnl_usd": round(float(df_equity["equity"].iloc[-1]) - 10000.0, 2),
        },
        "committee_performance": {
            "total_return_pct": round(tear_sheet.total_return_pct * 100.0, 2),
            "annualized_return_pct": round(tear_sheet.cagr_pct * 100.0, 2),
            "annualized_sharpe": round(tear_sheet.annualized_sharpe, 2),
            "sortino_ratio": round(tear_sheet.annualized_sortino, 2),
            "max_drawdown_pct": round(tear_sheet.max_drawdown_pct * 100.0, 2),
            "calmar_ratio": round(tear_sheet.calmar_ratio, 2),
            "total_trades": tear_sheet.total_trades,
            "winning_trades": tear_sheet.winning_trades,
            "losing_trades": tear_sheet.losing_trades,
            "win_rate_pct": round(tear_sheet.win_rate_pct * 100.0, 1),
            "profit_factor": round(tear_sheet.profit_factor, 2),
            "payoff_ratio": round(tear_sheet.payoff_ratio, 2),
            "expectancy_usd": round(tear_sheet.avg_trade_pnl_usd, 2),
            "market_exposure_pct": round(tear_sheet.exposure_time_pct * 100.0, 1),
        },
        "risk_analytics": {
            "cornish_fisher_var_95_pct": round(var_summary.get("cornish_fisher_var_95", 0.0) * 100.0, 3),
            "historical_var_95_pct": round(var_summary.get("historical_var_95", 0.0) * 100.0, 3),
            "cvar_95_pct": round(var_summary.get("cvar_95", 0.0) * 100.0, 3),
            "skewness": round(var_summary.get("skewness", 0.0), 3),
            "kurtosis": round(var_summary.get("kurtosis", 0.0), 3),
        },
        "monthly_breakdown": monthly_stats,
        "regime_distribution_pct": regime_dist,
        "species_benchmarks": species_results,
    }

    # Save to disk
    json_path = OUTPUT_DIR / "backtest_results_6m.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2)

    csv_path = OUTPUT_DIR / "backtest_equity_curve_6m.csv"
    df_equity.to_csv(csv_path, index=False)

    logger.info(f"Results successfully saved to {json_path} and {csv_path}")
    logger.info("=================================================================")
    logger.info(f"Committee Total Return: {final_output['committee_performance']['total_return_pct']:+.2f}%")
    logger.info(f"Committee Sharpe Ratio: {final_output['committee_performance']['annualized_sharpe']:.2f}")
    logger.info(f"Committee Max Drawdown: {final_output['committee_performance']['max_drawdown_pct']:.2f}%")
    logger.info(f"Committee Win Rate:     {final_output['committee_performance']['win_rate_pct']:.1f}%")
    logger.info(f"Committee Profit Factor:{final_output['committee_performance']['profit_factor']:.2f}")
    logger.info("=================================================================")


if __name__ == "__main__":
    asyncio.run(main())
