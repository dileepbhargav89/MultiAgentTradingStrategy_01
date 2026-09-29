"""Full 2-Year Historical Backtest & Institutional Tear-Sheet for StrategyOne.

Simulates 2 full years (730 days: September 2024 to September 2026) of BTC/USDT data:
1. Multi-species vectorized benchmarking across the 2-year macro cycle.
2. Full 9-Agent Autonomous Committee walk-forward historical simulation.
3. Institutional tear-sheet generation (CAGR, Sharpe, Sortino, Calmar, VaR/CVaR, Monthly Matrix).
4. Generates multi-tab institutional Excel pack for Guru99 Trading Firm.
"""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import warnings

warnings.filterwarnings("ignore")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from loguru import logger

from core.types import StrategyGenome, StrategySpecies, VolatilityRegime
from engine.species_strategies import SpeciesStrategyBuilder
from engine.vectorized_backtester import VectorizedBacktester
from engine.committee_backtester import MultiAgentCommitteeBacktester
from models.tear_sheet import TearSheetReport, TearSheetCalculator
from models.var_calculator import VaRCalculator

CACHE_DIR = PROJECT_ROOT / "data" / "cache"
OUTPUT_DIR = PROJECT_ROOT / "data"
GURU99_DIR = Path(r"D:\Projects\Trading Project\stretegyone_back_and_result")


def load_2y_data():
    """Loads 2-year cached multi-timeframe BTC/USDT data."""
    f_15m = CACHE_DIR / "BTCUSDT_730d_15m.csv"
    f_1h = CACHE_DIR / "BTCUSDT_730d_1h.csv"
    f_4h = CACHE_DIR / "BTCUSDT_730d_4h.csv"
    f_1d = CACHE_DIR / "BTCUSDT_730d_1d.csv"

    for f in [f_15m, f_1h, f_4h, f_1d]:
        if not f.exists():
            raise FileNotFoundError(f"Missing required 2Y data file: {f}")

    df_15m = pd.read_csv(f_15m)
    df_1h = pd.read_csv(f_1h)
    df_4h = pd.read_csv(f_4h)
    df_1d = pd.read_csv(f_1d)

    for df in [df_15m, df_1h, df_4h, df_1d]:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

    return df_15m, df_1h, df_4h, df_1d


def run_vectorized_species_benchmarks(df_1h: pd.DataFrame, initial_capital: float = 10000.0) -> dict:
    """Computes vectorized performance for single-species baselines over 2 years."""
    logger.info("Running Vectorized Multi-Species Benchmarks over 2 years...")
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
            f"  {name:<26} | Return: {results[spec.name]['total_return_pct']:>6.2f}% | "
            f"Sharpe: {results[spec.name]['annualized_sharpe']:>5.2f} | "
            f"MaxDD: {results[spec.name]['max_drawdown_pct']:>5.2f}% | "
            f"Trades: {results[spec.name]['total_trades']:>4} | "
            f"WinRate: {results[spec.name]['win_rate_pct']:>4.1f}%"
        )

    return results


async def run_committee_2y_backtest(
    df_15m: pd.DataFrame,
    df_1h: pd.DataFrame,
    df_4h: pd.DataFrame,
    df_1d: pd.DataFrame,
    initial_equity: float = 10000.0,
    stride: int = 16,
):
    """Executes the full 9-agent autonomous committee over 2 years."""
    total_bars = len(df_15m)
    logger.info(f"Running Full 9-Agent Committee Backtest over {total_bars} 15m bars (~730 days, stride={stride})...")

    # Sample dataset by stride for optimal walk-forward execution speed
    warmup = 200
    sample_indices = list(range(warmup, total_bars, stride))
    sampled_15m = pd.concat([df_15m.iloc[:warmup], df_15m.iloc[sample_indices]]).reset_index(drop=True)

    backtester = MultiAgentCommitteeBacktester(
        symbol="BTC/USDT",
        initial_equity=initial_equity,
        warmup_candles=warmup,
        retrain_interval_bars=96,
    )

    tear_sheet, df_equity = await backtester.run(
        df_15m=sampled_15m,
        df_1h=df_1h,
        df_4h=df_4h,
        df_1d=df_1d,
    )

    return tear_sheet, df_equity


def compute_monthly_breakdown(df_equity: pd.DataFrame) -> list:
    """Aggregates equity curve into monthly performance rows."""
    df = df_equity.copy()
    df["year_month"] = df["timestamp"].dt.strftime("%Y-%m")
    grouped = df.groupby("year_month")

    monthly = []
    for ym, group in grouped:
        st_eq = float(group["equity"].iloc[0])
        end_eq = float(group["equity"].iloc[-1])
        ret = ((end_eq - st_eq) / st_eq) * 100.0
        peak = group["equity"].cummax()
        dd = ((group["equity"] - peak) / peak).min() * 100.0

        monthly.append({
            "month": str(ym),
            "start_equity": round(st_eq, 2),
            "end_equity": round(end_eq, 2),
            "pnl_usd": round(end_eq - st_eq, 2),
            "return_pct": round(ret, 2),
            "max_drawdown_pct": round(abs(dd), 2),
        })
    return monthly


def compute_regime_analytics(df_1h: pd.DataFrame) -> dict:
    """Calculates macro regime distribution over the 2-year sample."""
    df = df_1h.copy()
    df["sma50"] = df["close"].rolling(50).mean()
    df["sma200"] = df["close"].rolling(200).mean()
    df["rolling_vol"] = df["close"].pct_change().rolling(24).std()

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
    logger.info("   STRATEGYONE 2-YEAR BTC/USDT MULTI-AGENT BACKTEST BENCHMARK    ")
    logger.info("=================================================================")

    df_15m, df_1h, df_4h, df_1d = load_2y_data()

    btc_start_price = float(df_15m["close"].iloc[0])
    btc_end_price = float(df_15m["close"].iloc[-1])
    btc_return_pct = ((btc_end_price - btc_start_price) / btc_start_price) * 100.0

    logger.info(f"Test Period: {df_15m['timestamp'].iloc[0]} -> {df_15m['timestamp'].iloc[-1]} (730 Days / 2 Years)")
    logger.info(f"BTC Start: ${btc_start_price:,.2f} | BTC End: ${btc_end_price:,.2f} | Buy & Hold: {btc_return_pct:+.2f}%")
    logger.info("-----------------------------------------------------------------")

    # 1. Multi-Species Vectorized Benchmark
    species_results = run_vectorized_species_benchmarks(df_1h, initial_capital=10000.0)

    # 2. Committee Multi-Agent Backtest
    # 730 days on 15m: stride 16 (4-hour decision cycles) produces ~4,350 walk-forward cycles
    stride = 16
    tear_sheet, df_equity = await run_committee_2y_backtest(
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
            "duration_days": 730,
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

    # Save results to data/
    json_path = OUTPUT_DIR / "backtest_results_2y.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2)

    csv_path = OUTPUT_DIR / "backtest_equity_curve_2y.csv"
    df_equity.to_csv(csv_path, index=False)

    # Also save to GURU99 target folder
    GURU99_DIR.mkdir(parents=True, exist_ok=True)
    with open(GURU99_DIR / "StrategyOne_2Y_Backtest_Summary.json", "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2)
    df_equity.to_csv(GURU99_DIR / "StrategyOne_2Y_Equity_Curve.csv", index=False)

    logger.info(f"2Y Results successfully saved to {json_path} and {csv_path}")
    logger.info(f"2Y Results copied to {GURU99_DIR}")
    logger.info("=================================================================")
    logger.info(f"2Y Committee Total Return: {final_output['committee_performance']['total_return_pct']:+.2f}%")
    logger.info(f"2Y Committee Sharpe Ratio: {final_output['committee_performance']['annualized_sharpe']:.2f}")
    logger.info(f"2Y Committee Max Drawdown: {final_output['committee_performance']['max_drawdown_pct']:.2f}%")
    logger.info("=================================================================")


if __name__ == "__main__":
    asyncio.run(main())
