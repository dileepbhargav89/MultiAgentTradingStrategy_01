"""
Recomputes tear-sheet metrics for trade stats and updates JSON and Excel presentation.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import json
import numpy as np
import pandas as pd
import openpyxl

from scripts.run_2y_backtest_v2 import generate_guru99_institutional_excel

DEST_DIR = Path(r"D:\Projects\Trading Project\stretegyone_back_and_result")
DATA_DIR = Path("data")

def main():
    json_path = DEST_DIR / "StrategyOne_2Y_Backtest_Summary.json"
    equity_path = DEST_DIR / "StrategyOne_2Y_Equity_Curve.csv"
    daily_path = DEST_DIR / "StrategyOne_2Y_Daily_Ledger.csv"
    excel_path = DEST_DIR / "StrategyOne_Institutional_TearSheet_BTC_2Y.xlsx"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    df_equity = pd.read_csv(equity_path)
    daily_df = pd.read_csv(daily_path)
    trade_history = data.get("trade_history", [])

    # Trade stats calculation
    pnls = [float(t.get("net_pnl", t.get("gross_pnl", t.get("realized_pnl_usd", 0.0)))) for t in trade_history]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    tot_trades = len(pnls)
    win_cnt = len(wins)
    loss_cnt = len(losses)
    win_rate = (win_cnt / tot_trades * 100.0) if tot_trades > 0 else 0.0

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 1e-6 else 99.0

    avg_pnl = float(np.mean(pnls)) if pnls else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(abs(np.mean(losses))) if losses else 0.0
    payoff_ratio = (avg_win / avg_loss) if avg_loss > 1e-6 else avg_win

    # Update committee performance
    perf = data["committee_performance"]
    perf["total_trades"] = tot_trades
    perf["winning_trades"] = win_cnt
    perf["losing_trades"] = loss_cnt
    perf["win_rate_pct"] = round(win_rate, 1)
    perf["profit_factor"] = round(profit_factor, 2)
    perf["payoff_ratio"] = round(payoff_ratio, 2)
    perf["expectancy_usd"] = round(avg_pnl, 2)

    print("=== UPDATED TEAR SHEET TRADE STATS ===")
    print(f"Total Trades:   {tot_trades}")
    print(f"Winning Trades: {win_cnt} ({win_rate:.1f}%)")
    print(f"Losing Trades:  {loss_cnt}")
    print(f"Gross Profit:   ${gross_profit:,.2f}")
    print(f"Gross Loss:     ${gross_loss:,.2f}")
    print(f"Profit Factor:  {profit_factor:.2f}")
    print(f"Avg Win:        ${avg_win:,.2f}")
    print(f"Avg Loss:       ${avg_loss:,.2f}")
    print(f"Payoff Ratio:   {payoff_ratio:.2f}")
    print(f"Expectancy:     ${avg_pnl:,.2f} / trade")

    # Save updated JSONs
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    with open(DATA_DIR / "backtest_results_2y_v2.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Regenerate 8-Sheet Institutional Excel
    generate_guru99_institutional_excel(
        results=data,
        df_equity=df_equity,
        daily_df=daily_df,
        monthly=data.get("monthly_breakdown", []),
        benchmarks=data.get("species_benchmarks", {}),
        regime_dist=data.get("regime_distribution_pct", {}),
        trade_history=trade_history,
        output_path=excel_path,
    )
    print(f"Successfully regenerated institutional Excel at: {excel_path}")

if __name__ == "__main__":
    main()
