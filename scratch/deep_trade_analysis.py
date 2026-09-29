import json
import pandas as pd
import numpy as np

d = json.load(open('data/backtest_results_2y_v2.json'))
trades = d['trade_history']
df = pd.DataFrame(trades)

print("Columns:", df.columns.tolist())
df['win'] = df['net_pnl'] > 0
print(f"Total trades: {len(df)}, Wins: {df['win'].sum()}, Win Rate: {df['win'].mean():.2%}")

# Print first trade to see all fields
print("\nSample trade keys/values:")
for k, v in trades[0].items():
    print(f"  {k}: {v}")

print("\n--- BY EXIT REASON ---")
for reason, g in df.groupby('exit_reason'):
    print(f"{reason:<22} Count: {len(g):<4} WR: {g['win'].mean():.1%} NetPnL: ${g['net_pnl'].sum():>8.2f} AvgPnL: ${g['net_pnl'].mean():>6.2f}")

print("\n--- BY SIDE ---")
for side, g in df.groupby('side'):
    print(f"{side:<10} Count: {len(g):<4} WR: {g['win'].mean():.1%} NetPnL: ${g['net_pnl'].sum():>8.2f} AvgPnL: ${g['net_pnl'].mean():>6.2f}")

# Check notional brackets
df['notional'] = df['quantity'] * df['entry_price']
df['notional_bin'] = pd.qcut(df['notional'], q=5)
print("\n--- BY NOTIONAL QUINTILE ---")
for bin_name, g in df.groupby('notional_bin'):
    print(f"{str(bin_name):<25} Count: {len(g):<4} WR: {g['win'].mean():.1%} NetPnL: ${g['net_pnl'].sum():>8.2f} AvgPnL: ${g['net_pnl'].mean():>6.2f}")

# Check holding duration
if 'entry_time' in df.columns and 'exit_time' in df.columns:
    df['entry_dt'] = pd.to_datetime(df['entry_time'])
    df['exit_dt'] = pd.to_datetime(df['exit_time'])
    df['duration_hours'] = (df['exit_dt'] - df['entry_dt']).dt.total_seconds() / 3600.0
    print("\n--- DURATION STATS ---")
    print(f"Avg duration winners: {df[df['win']]['duration_hours'].mean():.1f}h")
    print(f"Avg duration losers:  {df[~df['win']]['duration_hours'].mean():.1f}h")
    df['duration_bin'] = pd.cut(df['duration_hours'], bins=[0, 1, 4, 12, 24, 48, 1000])
    for bin_name, g in df.groupby('duration_bin'):
        print(f"{str(bin_name):<20} Count: {len(g):<4} WR: {g['win'].mean():.1%} NetPnL: ${g['net_pnl'].sum():>8.2f}")
