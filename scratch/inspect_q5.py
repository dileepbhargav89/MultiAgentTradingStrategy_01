import json
import pandas as pd
import numpy as np

with open('data/backtest_results_2y_v2.json') as f:
    data = json.load(f)

trades = data.get('trade_history', [])
df = pd.DataFrame(trades)
df['notional'] = df['quantity'] * df['entry_price']
q5_cutoff = df['notional'].quantile(0.80)

q5 = df[df['notional'] >= q5_cutoff]
non_q5 = df[df['notional'] < q5_cutoff]

print(f"Q5 Count: {len(q5)}, Net PnL: ${q5['net_pnl'].sum():.2f}, Win Rate: {(q5['net_pnl']>0).mean()*100:.1f}%")
print(f"Non-Q5 Count: {len(non_q5)}, Net PnL: ${non_q5['net_pnl'].sum():.2f}, Win Rate: {(non_q5['net_pnl']>0).mean()*100:.1f}%")

print("\n--- Q5 Return Pct vs Non-Q5 Return Pct ---")
print(f"Q5 Avg Return %: {q5['return_pct'].mean():.2f}% (Win: {q5[q5['net_pnl']>0]['return_pct'].mean():.2f}%, Loss: {q5[q5['net_pnl']<=0]['return_pct'].mean():.2f}%)")
print(f"Non-Q5 Avg Return %: {non_q5['return_pct'].mean():.2f}% (Win: {non_q5[non_q5['net_pnl']>0]['return_pct'].mean():.2f}%, Loss: {non_q5[non_q5['net_pnl']<=0]['return_pct'].mean():.2f}%)")

print("\n--- Q5 Exit Reasons ---")
print(q5['exit_reason'].value_counts())
print("\n--- Non-Q5 Exit Reasons ---")
print(non_q5['exit_reason'].value_counts())

print("\n--- Q5 Entry Prices and Dates ---")
q5_sample = q5[['timestamp', 'side', 'entry_price', 'exit_price', 'quantity', 'notional', 'return_pct', 'net_pnl', 'exit_reason']].head(15)
print(q5_sample.to_string())

# When did Q5 trades occur?
q5['dt'] = pd.to_datetime(q5['timestamp'])
print("\nQ5 Monthly Distribution:")
print(q5['dt'].dt.to_period('M').value_counts().sort_index())
