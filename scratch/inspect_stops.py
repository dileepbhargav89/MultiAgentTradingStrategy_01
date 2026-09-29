import json
import pandas as pd
import numpy as np

d = json.load(open('data/backtest_results_2y_v2.json'))
trades = d['trade_history']
df = pd.DataFrame(trades)
df['notional'] = df['quantity'] * df['entry_price']
df['win'] = df['net_pnl'] > 0
# Compute actual price change pct
df['price_move_pct'] = abs(df['exit_price'] - df['entry_price']) / df['entry_price'] * 100

# Stop loss trades only
sl_trades = df[df['exit_reason'] == 'STOP_LOSS'].copy()
print("Stop Loss Trades Price Move %:")
print(sl_trades['price_move_pct'].describe())

print("\n--- TRADES BY PRICE MOVE PCT AT EXIT (FOR ALL TRADES) ---")
df['exit_pct_bracket'] = pd.cut(df['price_move_pct'], bins=[0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 5.0, 50.0])
for b, g in df.groupby('exit_pct_bracket'):
    print(f"{str(b):<20} Count: {len(g):<4} WR: {g['win'].mean():.1%} NetPnL: ${g['net_pnl'].sum():>8.2f} AvgPnL: ${g['net_pnl'].mean():>6.2f}")
