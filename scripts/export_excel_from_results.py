"""Export Institutional Excel Pack from Completed 2-Year Backtest Cache.

Generates the 8-sheet institutional Excel workbook, daily ledger, equity curves,
and JSON summaries for Guru99 Trading Firm.
"""

import json
from pathlib import Path
import sys
import pandas as pd
from loguru import logger

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.run_2y_backtest_v2 import (
    generate_guru99_institutional_excel,
    compute_daily_breakdown,
)
from models.var_calculator import VaRCalculator

OUTPUT_DIR = Path(PROJECT_ROOT) / "data"
DEST_DIR = Path(r"D:\Projects\Trading Project\stretegyone_back_and_result")


def main():
    json_path = OUTPUT_DIR / "backtest_results_2y_v2.json"
    csv_equity_path = OUTPUT_DIR / "backtest_equity_curve_2y_v2.csv"

    if not json_path.exists() or not csv_equity_path.exists():
        logger.error(f"Missing backtest results cache at {json_path} or {csv_equity_path}")
        return

    logger.info(f"Loading results from {json_path}...")
    with open(json_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    df_equity = pd.read_csv(csv_equity_path)
    daily_df = compute_daily_breakdown(df_equity)

    # Compute accurate VaR and CVaR analytics from the equity curve
    equity_returns = df_equity["equity"].pct_change().dropna().values
    portfolio_equity = float(df_equity["equity"].iloc[-1])
    var_summary = VaRCalculator.compute_risk_summary(
        equity_returns,
        portfolio_equity=portfolio_equity,
        timeframe="1h",
    )
    results["risk_analytics"] = {
        "cornish_fisher_var_95_pct": round(
            var_summary.get("cornish_fisher_var_95_pct", 0.0) * 100.0, 3
        ),
        "historical_var_95_pct": round(
            var_summary.get("historical_var_95_pct", 0.0) * 100.0, 3
        ),
        "parametric_var_95_pct": round(
            var_summary.get("parametric_var_95_pct", 0.0) * 100.0, 3
        ),
        "cvar_95_pct": round(
            var_summary.get("cvar_expected_shortfall_95_pct", 0.0) * 100.0, 3
        ),
        "var_95_1day_usd": round(var_summary.get("var_95_1day_usd", 0.0), 2),
        "cvar_95_1day_usd": round(var_summary.get("cvar_95_1day_usd", 0.0), 2),
        "skewness": round(var_summary.get("skewness", 0.0), 3),
        "kurtosis": round(var_summary.get("excess_kurtosis", 0.0), 3),
    }

    monthly_stats = results.get("monthly_breakdown", [])
    species_results = results.get("species_benchmarks", {})
    regime_dist = results.get("regime_distribution_pct", {})
    trade_history = results.get("trade_history", [])

    DEST_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Update Destination JSON
    dest_json = DEST_DIR / "StrategyOne_2Y_Backtest_Summary.json"
    with open(dest_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Saved: {dest_json}")

    # 2. Update Destination CSVs
    dest_equity = DEST_DIR / "StrategyOne_2Y_Equity_Curve.csv"
    df_equity.to_csv(dest_equity, index=False)
    logger.info(f"Saved: {dest_equity}")

    dest_daily = DEST_DIR / "StrategyOne_2Y_Daily_Ledger.csv"
    daily_df.to_csv(dest_daily, index=False)
    logger.info(f"Saved: {dest_daily}")

    # 3. Generate Institutional Excel Workbook
    excel_path = DEST_DIR / "StrategyOne_Institutional_TearSheet_BTC_2Y.xlsx"
    clean_excel_path = DEST_DIR / "StrategyOne_Institutional_TearSheet_BTC_2Y_Clean.xlsx"

    logger.info(f"Generating 8-sheet Excel workbook at {excel_path}...")
    generate_guru99_institutional_excel(
        results=results,
        df_equity=df_equity,
        daily_df=daily_df,
        monthly=monthly_stats,
        benchmarks=species_results,
        regime_dist=regime_dist,
        trade_history=trade_history,
        output_path=excel_path,
    )

    # Also save a dedicated clean copy so the user has immediate access even if the original is locked in Excel
    generate_guru99_institutional_excel(
        results=results,
        df_equity=df_equity,
        daily_df=daily_df,
        monthly=monthly_stats,
        benchmarks=species_results,
        regime_dist=regime_dist,
        trade_history=trade_history,
        output_path=clean_excel_path,
    )
    logger.info(f"Also saved clean copy at {clean_excel_path}")

    # 4. Print Summary
    perf = results["committee_performance"]
    meta = results["metadata"]
    logger.info("=" * 80)
    logger.info("   2-YEAR INSTITUTIONAL BACKTEST REPORT GENERATED SUCCESSFULLY   ")
    logger.info("=" * 80)
    logger.info(f"  Total Trades:       {perf['total_trades']}")
    logger.info(f"  Win Rate:           {perf['win_rate_pct']:.1f}%")
    logger.info(f"  Payoff Ratio:       {perf.get('payoff_ratio', 0.0):.2f}")
    logger.info(f"  Profit Factor:      {perf['profit_factor']:.2f}")
    logger.info(f"  Max Drawdown:       {perf['max_drawdown_pct']:.2f}%")
    logger.info(f"  Sharpe Ratio:       {perf['annualized_sharpe']:.2f}")
    logger.info(f"  Net Total Return:   {perf['total_return_pct']:+.2f}%")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
