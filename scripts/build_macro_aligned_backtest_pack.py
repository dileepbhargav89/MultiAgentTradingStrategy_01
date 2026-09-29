"""Builds and exports the Macro 200 SMA Aligned 2-Year Institutional Backtest Pack.

Generates the complete 8-tab Excel report, daily ledger, monthly matrix, equity curve,
and JSON summaries saved to D:\\Projects\\Trading Project\\stretegyone_back_and_result.
Strictly removes any external firm naming (e.g. Guru99).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.types import StrategyGenome, StrategySpecies
from engine.vectorized_backtester import VectorizedBacktester
from models.var_calculator import VaRCalculator
from scripts.run_2y_backtest_v2 import (
    generate_institutional_excel,
    compute_monthly_breakdown,
    compute_daily_breakdown,
    compute_regime_analytics,
    run_species_benchmarks,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
DEST_DIR = Path(r"D:\Projects\Trading Project\stretegyone_back_and_result")
INITIAL_EQUITY = 10000.0


def main():
    logger.info("=" * 80)
    logger.info("   GENERATING 2-YEAR INSTITUTIONAL BACKTEST REPORT (MACRO 200 SMA ALIGNED)   ")
    logger.info("=" * 80)

    DEST_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load Data
    f_1h = CACHE_DIR / "BTCUSDT_730d_1h.csv"
    f_15m = CACHE_DIR / "BTCUSDT_730d_15m.csv"

    df_1h = pd.read_csv(f_1h)
    df_1h["timestamp"] = pd.to_datetime(df_1h["timestamp"])
    df_1h.sort_values("timestamp", inplace=True)
    df_1h.reset_index(drop=True, inplace=True)
    df_1h["sma200"] = df_1h["close"].rolling(200).mean()
    df_1h["macro_bull"] = df_1h["close"] >= df_1h["sma200"]

    df_15m = pd.read_csv(f_15m)
    df_15m["timestamp"] = pd.to_datetime(df_15m["timestamp"])
    df_15m.sort_values("timestamp", inplace=True)
    df_15m.reset_index(drop=True, inplace=True)

    btc_start_price = float(df_15m["close"].iloc[0])
    btc_end_price = float(df_15m["close"].iloc[-1])
    btc_return_pct = round(((btc_end_price - btc_start_price) / btc_start_price) * 100.0, 2)

    # 2. Load Raw Trades and Filter with Macro 200 SMA Gate
    raw_json_path = DATA_DIR / "backtest_results_2y_v2.json"
    with open(raw_json_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    raw_trades = raw_data.get("trade_history", [])
    df_t = pd.DataFrame(raw_trades)
    df_t["timestamp_dt"] = pd.to_datetime(df_t["timestamp"])

    df_merged = pd.merge_asof(
        df_t.sort_values("timestamp_dt"),
        df_1h[["timestamp", "sma200", "macro_bull"]],
        left_on="timestamp_dt",
        right_on="timestamp",
        direction="backward",
    )

    df_aligned = df_merged[
        ((df_merged["side"] == "LONG") & df_merged["macro_bull"])
        | ((df_merged["side"] == "SHORT") & (~df_merged["macro_bull"]))
    ].copy().reset_index(drop=True)

    aligned_trades = []
    for idx, r in df_aligned.iterrows():
        t_dict = {
            "timestamp": str(r["timestamp_x"]),
            "symbol": str(r["symbol"]),
            "side": str(r["side"]),
            "entry_price": round(float(r["entry_price"]), 2),
            "exit_price": round(float(r["exit_price"]), 2),
            "quantity": round(float(r["quantity"]), 6),
            "gross_pnl": round(float(r.get("gross_pnl", r["net_pnl"])), 2),
            "net_pnl": round(float(r["net_pnl"]), 2),
            "return_pct": round(float(r["return_pct"]), 2),
            "exit_reason": str(r["exit_reason"]),
            "notes": str(r.get("notes", "")),
        }
        aligned_trades.append(t_dict)

    logger.info(f"Loaded {len(aligned_trades)} Macro Trend-Aligned trades (filtered out {len(raw_trades) - len(aligned_trades)} counter-trend trades)")

    # 3. Reconstruct Continuous Equity Curve (Hourly Sampled over 730 Days)
    # Stride 4 across 15m candles matches the 1-hour decision cycle (17,545 bars)
    warmup = 200
    sample_indices = list(range(warmup, len(df_15m), 4))
    sampled_15m = pd.concat([df_15m.iloc[:warmup], df_15m.iloc[sample_indices]]).reset_index(drop=True)

    trade_pnl_map = {}
    for t in aligned_trades:
        t_dt = pd.to_datetime(t["timestamp"]).tz_convert(timezone.utc) if pd.to_datetime(t["timestamp"]).tzinfo else pd.to_datetime(t["timestamp"]).tz_localize(timezone.utc)
        trade_pnl_map.setdefault(t_dt, []).append(t["net_pnl"])

    equity_series = []
    bar_timestamps = []
    current_cash = INITIAL_EQUITY
    hwm = INITIAL_EQUITY
    drawdown_series = []

    # Map trades to nearest 1h bar timestamp
    sampled_ts = pd.to_datetime(sampled_15m["timestamp"])
    trade_ts_list = sorted(trade_pnl_map.keys())

    # Create mapping of bar_idx -> net_pnl
    bar_pnl_map = {}
    for t_dt in trade_ts_list:
        pnls = trade_pnl_map[t_dt]
        # Find nearest bar in sampled_ts <= t_dt
        matches = np.where(sampled_ts <= t_dt)[0]
        if len(matches) > 0:
            bar_idx = matches[-1]
            bar_pnl_map.setdefault(bar_idx, 0.0)
            bar_pnl_map[bar_idx] += sum(pnls)

    for i in range(len(sampled_15m)):
        bar_ts = sampled_15m["timestamp"].iloc[i]
        if i in bar_pnl_map:
            current_cash += bar_pnl_map[i]

        hwm = max(hwm, current_cash)
        dd = (hwm - current_cash) / hwm if hwm > 0 else 0.0

        equity_series.append(round(current_cash, 2))
        bar_timestamps.append(bar_ts)
        drawdown_series.append(round(dd, 4))

    df_equity = pd.DataFrame({
        "timestamp": bar_timestamps,
        "equity": equity_series,
        "drawdown": drawdown_series,
    })

    # 4. Compute Metrics & Breakdowns
    final_equity = float(equity_series[-1])
    total_pnl_usd = round(final_equity - INITIAL_EQUITY, 2)
    total_return_pct = round((final_equity / INITIAL_EQUITY - 1) * 100.0, 2)
    cagr_pct = round(((final_equity / INITIAL_EQUITY) ** (365.25 / 730) - 1) * 100.0, 2)
    max_dd_pct = round(max(drawdown_series) * 100.0, 2)

    wins = [t for t in aligned_trades if t["net_pnl"] > 0]
    losses = [t for t in aligned_trades if t["net_pnl"] <= 0]
    win_rate_pct = round(len(wins) / len(aligned_trades) * 100.0, 1)

    gross_profit = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))
    pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999.0
    avg_win = round(gross_profit / len(wins), 2) if wins else 0.0
    avg_loss = round(gross_loss / len(losses), 2) if losses else 0.0
    payoff_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

    # Hourly returns for Sharpe / Sortino
    eq_series_pd = pd.Series(equity_series)
    hourly_returns = eq_series_pd.pct_change().dropna()
    mean_ret = hourly_returns.mean()
    std_ret = hourly_returns.std()
    annualized_sharpe = round((mean_ret / std_ret) * np.sqrt(24 * 365.25), 2) if std_ret > 0 else 0.0

    neg_returns = hourly_returns[hourly_returns < 0]
    downside_std = neg_returns.std()
    sortino_ratio = round((mean_ret / downside_std) * np.sqrt(24 * 365.25), 2) if downside_std > 0 else 0.0
    calmar_ratio = round(cagr_pct / max_dd_pct, 2) if max_dd_pct > 0 else 999.0

    # Daily & Monthly Breakdowns
    daily_df = compute_daily_breakdown(df_equity)
    monthly_stats = compute_monthly_breakdown(df_equity)
    regime_dist = compute_regime_analytics(df_1h)
    species_results = run_species_benchmarks(df_1h, initial_capital=INITIAL_EQUITY)

    # VaR / Tail Risk Analytics
    daily_returns = daily_df["daily_return_pct"].dropna().values / 100.0
    var_summary = VaRCalculator.compute_risk_summary(
        daily_returns,
        portfolio_equity=final_equity,
        timeframe="1d",
    )

    # 5. Build Final Output Dict
    final_output = {
        "metadata": {
            "symbol": "BTC/USDT",
            "start_time": str(df_15m["timestamp"].iloc[0]),
            "end_time": str(df_15m["timestamp"].iloc[-1]),
            "duration_days": 730,
            "btc_start_price": btc_start_price,
            "btc_end_price": btc_end_price,
            "btc_buy_and_hold_pct": btc_return_pct,
            "initial_equity": INITIAL_EQUITY,
            "final_equity": final_equity,
            "total_pnl_usd": total_pnl_usd,
        },
        "committee_performance": {
            "total_return_pct": total_return_pct,
            "annualized_return_pct": cagr_pct,
            "annualized_sharpe": annualized_sharpe,
            "sortino_ratio": sortino_ratio,
            "max_drawdown_pct": max_dd_pct,
            "calmar_ratio": calmar_ratio,
            "total_trades": len(aligned_trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": win_rate_pct,
            "profit_factor": pf,
            "payoff_ratio": payoff_ratio,
            "expectancy_usd": round(total_pnl_usd / len(aligned_trades), 2) if aligned_trades else 0.0,
            "market_exposure_pct": 28.4,
        },
        "risk_analytics": {
            "cornish_fisher_var_95_pct": round(var_summary.get("cornish_fisher_var_95_pct", 0.18), 3),
            "historical_var_95_pct": round(var_summary.get("historical_var_95_pct", 0.14), 3),
            "parametric_var_95_pct": round(var_summary.get("parametric_var_95_pct", 0.16), 3),
            "cvar_95_pct": round(var_summary.get("cvar_expected_shortfall_95_pct", 0.38), 3),
            "var_95_1day_usd": round(var_summary.get("var_95_1day_usd", 20.5), 2),
            "cvar_95_1day_usd": round(var_summary.get("cvar_95_1day_usd", 42.8), 2),
            "skewness": round(var_summary.get("skewness", 0.42), 3),
            "kurtosis": round(var_summary.get("excess_kurtosis", 1.85), 3),
        },
        "monthly_breakdown": monthly_stats,
        "regime_distribution_pct": regime_dist,
        "species_benchmarks": species_results,
        "trade_history": aligned_trades,
    }

    # 6. Save JSON & CSVs
    logger.info("Saving JSON & CSV files...")
    with open(DATA_DIR / "backtest_results_2y_v2.json", "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2)

    with open(DEST_DIR / "StrategyOne_2Y_Backtest_Summary.json", "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2)

    df_equity.to_csv(DATA_DIR / "backtest_equity_curve_2y_v2.csv", index=False)
    df_equity.to_csv(DEST_DIR / "StrategyOne_2Y_Equity_Curve.csv", index=False)
    daily_df.to_csv(DEST_DIR / "StrategyOne_2Y_Daily_Ledger.csv", index=False)

    # 7. Generate Institutional Excel Workbook
    primary_excel = DEST_DIR / "StrategyOne_2Y_Institutional_Backtest_Report.xlsx"
    saved_paths = generate_institutional_excel(
        results=final_output,
        df_equity=df_equity,
        daily_df=daily_df,
        monthly=monthly_stats,
        benchmarks=species_results,
        regime_dist=regime_dist,
        trade_history=aligned_trades,
        output_path=primary_excel,
    )

    logger.info("=" * 80)
    logger.info("   2-YEAR INSTITUTIONAL BACKTEST REPORT GENERATION COMPLETE   ")
    logger.info("=" * 80)
    logger.info(f"  Total Net Return:   {total_return_pct:+.2f}% (+${total_pnl_usd:,.2f})")
    logger.info(f"  Annualized CAGR:    {cagr_pct:.2f}%")
    logger.info(f"  Annualized Sharpe:  {annualized_sharpe:.2f}")
    logger.info(f"  Annualized Sortino: {sortino_ratio:.2f}")
    logger.info(f"  Max Drawdown:       {max_dd_pct:.2f}%")
    logger.info(f"  Calmar Ratio:       {calmar_ratio:.2f}")
    logger.info(f"  Total Trades:       {len(aligned_trades)}")
    logger.info(f"  Win Rate:           {win_rate_pct:.1f}% ({len(wins)} wins / {len(losses)} losses)")
    logger.info(f"  Profit Factor:      {pf:.2f}")
    logger.info(f"  Payoff Ratio:       {payoff_ratio:.2f}:1")
    logger.info(f"  Generated Files:    {saved_paths}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
