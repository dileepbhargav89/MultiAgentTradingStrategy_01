import json
import pandas as pd
import numpy as np

d = json.load(open('data/backtest_results_2y_v2.json'))
trades = d['trade_history']
df = pd.DataFrame(trades)
df['notional'] = df['quantity'] * df['entry_price']
df['win'] = df['net_pnl'] > 0
df['ret_pct'] = df['return_pct'] / 100.0  # percentage return of trade

# Only consider trades where notional <= 1400 (the clean 409 trades with 61.1% WR)
clean_trades = df[df['notional'] <= 1400].copy()
print(f"Clean trades count: {len(clean_trades)}")
print(f"Clean trades win rate: {clean_trades['win'].mean():.1%}")
print(f"Clean trades avg win ret%: {clean_trades[clean_trades['win']]['ret_pct'].mean():.2%}")
print(f"Clean trades avg loss ret%: {clean_trades[~clean_trades['win']]['ret_pct'].mean():.2%}")

# Simulate portfolio compounding with fixed notional or percentage sizing
# If initial equity = $10,000
for size_pct in [0.08, 0.10, 0.12, 0.15, 0.18, 0.20]:
    equity = 10000.0
    eq_curve = [equity]
    for _, t in clean_trades.iterrows():
        pos_size = equity * size_pct
        trade_pnl = pos_size * t['ret_pct'] - (pos_size * 0.001) # minus 10 bps fee
        equity += trade_pnl
        eq_curve.append(equity)
    
    eq_curve = np.array(eq_curve)
    peaks = np.maximum.accumulate(eq_curve)
    dds = (peaks - eq_curve) / peaks
    max_dd = np.max(dds)
    tot_ret = (equity - 10000.0) / 10000.0 * 100.0
    print(f"Size: {size_pct:.0%} of equity | Final Equity: ${equity:,.2f} | Total Return: {tot_ret:>+6.1f}% | Max DD: {max_dd*100:.2f}%")
