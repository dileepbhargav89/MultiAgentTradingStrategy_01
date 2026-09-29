"""Export Final Institutional Pack from 2-Year Real BTC/USDT Backtest Results."""

import json
from pathlib import Path
import sys
import pandas as pd
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_2y_backtest_v2 import (
    generate_guru99_institutional_excel,
    compute_daily_breakdown,
    compute_monthly_breakdown,
    compute_regime_analytics,
    run_species_benchmarks,
    INITIAL_EQUITY,
)

OUTPUT_DIR = PROJECT_ROOT / "data"
DEST_DIR = Path(r"D:\Projects\Trading Project\stretegyone_back_and_result")
CACHE_DIR = OUTPUT_DIR / "cache"

def main():
    logger.info("Starting Institutional Excel Pack & Tear Sheet Export...")
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load precomputed results
    json_path = OUTPUT_DIR / "backtest_results_2y_v2.json"
    with open(json_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    equity_csv_path = OUTPUT_DIR / "backtest_equity_curve_2y_v2.csv"
    df_equity = pd.read_csv(equity_csv_path)

    # 2. Compute breakdowns
    daily_df = compute_daily_breakdown(df_equity)
    monthly_stats = compute_monthly_breakdown(df_equity)

    # 3. Load 1h data for species benchmarks & regime stats
    df_1h = pd.read_csv(CACHE_DIR / "BTCUSDT_730d_1h.csv")
    df_1h["timestamp"] = pd.to_datetime(df_1h["timestamp"])
    regime_dist = compute_regime_analytics(df_1h)
    species_results = run_species_benchmarks(df_1h, initial_capital=INITIAL_EQUITY)

    trade_history = results.get("trade_history", [])

    # 4. Save JSON summary to DEST_DIR
    def safe_write_json(path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved: {path}")
        except PermissionError:
            fallback = path.parent / f"{path.stem}_Clean{path.suffix}"
            with open(fallback, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.warning(f"File locked. Saved fallback: {fallback}")

    def safe_write_csv(df, path):
        try:
            df.to_csv(path, index=False)
            logger.info(f"Saved: {path}")
        except PermissionError:
            fallback = path.parent / f"{path.stem}_Clean{path.suffix}"
            df.to_csv(fallback, index=False)
            logger.warning(f"File locked. Saved fallback: {fallback}")

    safe_write_json(DEST_DIR / "StrategyOne_2Y_Backtest_Summary.json", results)
    safe_write_csv(df_equity, DEST_DIR / "StrategyOne_2Y_Equity_Curve.csv")
    safe_write_csv(daily_df, DEST_DIR / "StrategyOne_2Y_Daily_Ledger.csv")

    # 5. Export institutional Excel pack to both local and destination
    excel_dest = DEST_DIR / "StrategyOne_Institutional_TearSheet_BTC_2Y.xlsx"
    excel_local = OUTPUT_DIR / "StrategyOne_Institutional_TearSheet_BTC_2Y.xlsx"

    logger.info("Building 8-Sheet Institutional Excel Workbook...")
    generate_guru99_institutional_excel(
        results=results,
        df_equity=df_equity,
        daily_df=daily_df,
        monthly=monthly_stats,
        benchmarks=species_results,
        regime_dist=regime_dist,
        trade_history=trade_history,
        output_path=excel_dest,
    )

    generate_guru99_institutional_excel(
        results=results,
        df_equity=df_equity,
        daily_df=daily_df,
        monthly=monthly_stats,
        benchmarks=species_results,
        regime_dist=regime_dist,
        trade_history=trade_history,
        output_path=excel_local,
    )

    logger.success("=" * 80)
    logger.success("EXPORT COMPLETED SUCCESSFULLY!")
    logger.success(f"Final Equity: ${results['metadata']['final_equity']:,.2f}")
    logger.success(f"Net Profit: ${results['metadata']['total_pnl_usd']:,.2f} ({results['committee_performance']['total_return_pct']:+.2f}%)")
    logger.success(f"Trades: {results['committee_performance']['total_trades']} | Win Rate: {results['committee_performance']['win_rate_pct']:.1f}%")
    logger.success(f"Sharpe Ratio: {results['committee_performance']['annualized_sharpe']:.2f} | Profit Factor: {results['committee_performance']['profit_factor']:.2f}")
    logger.success(f"Max Drawdown: {results['committee_performance']['max_drawdown_pct']:.2f}% | Calmar Ratio: {results['committee_performance']['calmar_ratio']:.2f}")
    logger.success("=" * 80)

if __name__ == "__main__":
    main()
