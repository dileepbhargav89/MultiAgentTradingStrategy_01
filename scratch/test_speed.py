import asyncio
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from engine.committee_backtester import MultiAgentCommitteeBacktester
from scripts.run_2y_backtest_v2 import load_or_fetch_2y_data

async def main():
    df_15m, df_1h, df_4h, df_1d = load_or_fetch_2y_data()
    # Take first 1000 bars
    stride = 4
    sample_indices = list(range(200, 200 + 400, stride))
    sampled_15m = pd.concat([df_15m.iloc[:200], df_15m.iloc[sample_indices]]).reset_index(drop=True)
    
    backtester = MultiAgentCommitteeBacktester(
        symbol="BTC/USDT",
        initial_equity=10000.0,
        warmup_candles=200,
        retrain_interval_bars=96,
        quiet=True,
    )
    t0 = time.time()
    tear_sheet, df_equity = await backtester.run(sampled_15m, df_1h, df_4h, df_1d)
    dt = time.time() - t0
    print(f"Ran {len(sampled_15m)} bars in {dt:.2f}s ({len(sampled_15m)/dt:.1f} bars/sec)")
    print(f"Total return: {tear_sheet.total_return_pct:.2%}, Trades: {tear_sheet.total_trades}")

if __name__ == "__main__":
    asyncio.run(main())
