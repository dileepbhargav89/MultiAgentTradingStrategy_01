import json
import pandas as pd
import numpy as np

with open('data/backtest_results_2y_v2.json') as f:
    data = json.load(f)

trades = data.get('trade_history', [])
df_t = pd.DataFrame(trades)
print(f"Total trades executed: {len(df_t)}")
df_t['timestamp'] = pd.to_datetime(df_t['timestamp'])

# Load 1h BTC data
df_1h = pd.read_csv('data/cache/BTCUSDT_730d_1h.csv')
df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'])
df_1h['sma200'] = df_1h['close'].rolling(200).mean()
df_1h['macro_bull'] = df_1h['close'] > df_1h['sma200']

df_merged = pd.merge_asof(
    df_t.sort_values('timestamp'),
    df_1h[['timestamp', 'sma200', 'macro_bull']],
    on='timestamp',
    direction='backward'
)

# Check how many trades were STILL counter-trend (LONG when macro_bull is False, or SHORT when macro_bull is True)
counter_trades = df_merged[
    ((df_merged['side'] == 'LONG') & (~df_merged['macro_bull'])) |
    ((df_merged['side'] == 'SHORT') & (df_merged['macro_bull']))
]
aligned_trades = df_merged[
    ((df_merged['side'] == 'LONG') & (df_merged['macro_bull'])) |
    ((df_merged['side'] == 'SHORT') & (~df_merged['macro_bull']))
]

print(f"Aligned Trades Count: {len(aligned_trades)} | PnL: ${aligned_trades['net_pnl'].sum():,.2f} | Win Rate: {(aligned_trades['net_pnl']>0).mean()*100:.1f}%")
print(f"Counter-Trend Trades Count: {len(counter_trades)} | PnL: ${counter_trades['net_pnl'].sum():,.2f} | Win Rate: {(counter_trades['net_pnl']>0).mean()*100:.1f}%")

print("\nBreakdown by macro_bull and side:")
print(df_merged.groupby(['macro_bull', 'side']).agg(
    count=('net_pnl', 'count'),
    total_pnl=('net_pnl', 'sum'),
    win_rate=('net_pnl', lambda x: (x > 0).mean() * 100)
).reset_index().to_string(index=False))
