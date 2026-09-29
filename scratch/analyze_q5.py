import json
import pandas as pd
import numpy as np

d = json.load(open('data/backtest_results_2y_v2.json'))
trades = d['trade_history']
df = pd.DataFrame(trades)
df['notional'] = df['quantity'] * df['entry_price']
df['win'] = df['net_pnl'] > 0

q5 = df[df['notional'] > 1495].copy()
q14 = df[df['notional'] <= 1495].copy()

print(f"Q5 trades: {len(q5)}")
print(f"Q5 Net PnL: ${q5['net_pnl'].sum():.2f}")
print(f"Q5 Win Rate: {q5['win'].mean():.1%}")

print(f"\nQ1-4 trades: {len(q14)}")
print(f"Q1-4 Net PnL: ${q14['net_pnl'].sum():.2f}")
print(f"Q1-4 Win Rate: {q14['win'].mean():.1%}")

# Compare stop distance in Q5 vs Q1-4
# return_pct is (exit - entry) / entry * 100
print("\nQ5 Exit reasons:")
print(q5['exit_reason'].value_counts())

print("\nQ5 Return % distribution:")
print(q5['return_pct'].describe())

print("\nQ1-4 Return % distribution:")
print(q14['return_pct'].describe())

# Look at notes of Q5 trades
print("\nFirst 10 Q5 trade notes:")
for n in q5['notes'].head(10):
    print(" ", n)
