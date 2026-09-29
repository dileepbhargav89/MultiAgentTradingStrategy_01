import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from engine.committee_backtester import MultiAgentCommitteeBacktester
from scripts.run_2y_backtest_v2 import load_or_fetch_2y_data

async def run_test(threshold, bars=1000):
    df_15m, df_1h, df_4h, df_1d = load_or_fetch_2y_data()
    stride = 4
    sample_indices = list(range(200, 200 + bars, stride))
    sampled_15m = pd.concat([df_15m.iloc[:200], df_15m.iloc[sample_indices]]).reset_index(drop=True)
    
    backtester = MultiAgentCommitteeBacktester(
        symbol="BTC/USDT",
        initial_equity=10000.0,
        warmup_candles=200,
        retrain_interval_bars=96,
        quiet=True,
    )
    # Patch consensus threshold on decider agent in backtester
    backtester_run = backtester.run
    
    # We can run directly
    tear_sheet, df_equity = await backtester.run(sampled_15m, df_1h, df_4h, df_1d)
    print(f"Threshold default: Ret={tear_sheet.total_return_pct:.2%}, WR={tear_sheet.win_rate_pct:.1%}, Trades={tear_sheet.total_trades}")

if __name__ == "__main__":
    asyncio.run(run_test(0.50, bars=1000))
