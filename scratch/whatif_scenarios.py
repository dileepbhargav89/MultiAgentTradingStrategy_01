import json
import pandas as pd
import numpy as np

d = json.load(open('data/backtest_results_2y_v2.json'))
trades = d['trade_history']
df = pd.DataFrame(trades)
df['notional'] = df['quantity'] * df['entry_price']
df['win'] = df['net_pnl'] > 0
df['price_move_pct'] = abs(df['exit_price'] - df['entry_price']) / df['entry_price']

print(f"Total trades: {len(df)}")
print(f"Original Net PnL: ${df['net_pnl'].sum():.2f}")
print(f"Original Win Rate: {df['win'].mean():.1%}")

# Scenario 1: Filter out trades where notional > $1,400 (or tight stop noise trap)
s1 = df[df['notional'] <= 1400]
print(f"\nScenario 1 (Notional <= $1400):")
print(f"Trades: {len(s1)} | Net PnL: ${s1['net_pnl'].sum():.2f} | Win Rate: {s1['win'].mean():.1%}")

# Scenario 2: What if we cap notional at $1,200 for all trades?
# For trades with notional > 1200, scale PnL down to $1200 notional
s2_pnls = []
for _, row in df.iterrows():
    n = row['notional']
    pnl = row['net_pnl']
    if n > 1200:
        scale = 1200.0 / n
        s2_pnls.append(pnl * scale)
    else:
        s2_pnls.append(pnl)
s2_pnls = pd.Series(s2_pnls)
print(f"\nScenario 2 (Hard Notional Cap $1,200):")
print(f"Trades: {len(df)} | Net PnL: ${s2_pnls.sum():.2f} | Win Rate: {(s2_pnls > 0).mean():.1%}")

# Scenario 3: Filter trades by price move at stop: what was the planned stop distance?
# In notes: e.g. "LONG STOP_LOSS | Entry: $63,779.99 Exit: $63,194.20 Ret: -0.96%"
# If we filter trades where exit loss was between -0.5% and -1.1%
s3 = df[~((df['exit_reason'] == 'STOP_LOSS') & (df['price_move_pct'] < 0.011))]
print(f"\nScenario 3 (Eliminating tight stopouts < 1.1%):")
print(f"Trades: {len(s3)} | Net PnL: ${s3['net_pnl'].sum():.2f} | Win Rate: {s3['win'].mean():.1%}")
