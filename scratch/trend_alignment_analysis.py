import json
import pandas as pd
import numpy as np

with open('data/backtest_results_2y_v2.json') as f:
    data = json.load(f)

trades = data.get('trade_history', [])
df_t = pd.DataFrame(trades)
df_t['timestamp'] = pd.to_datetime(df_t['timestamp'])
df_t['notional'] = df_t['quantity'] * df_t['entry_price']

# Load 1h BTC data to get 200 EMA / 50 SMA macro trend
df_1h = pd.read_csv('data/cache/BTCUSDT_730d_1h.csv')
df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'])
df_1h['sma50'] = df_1h['close'].rolling(50).mean()
df_1h['sma200'] = df_1h['close'].rolling(200).mean()
df_1h['macro_bull'] = df_1h['close'] > df_1h['sma200']
df_1h['trend_bull'] = (df_1h['close'] > df_1h['sma50']) & (df_1h['sma50'] > df_1h['sma200'])
df_1h['trend_bear'] = (df_1h['close'] < df_1h['sma50']) & (df_1h['sma50'] < df_1h['sma200'])

# Merge macro trend to trades
df_merged = pd.merge_asof(
    df_t.sort_values('timestamp'),
    df_1h[['timestamp', 'sma50', 'sma200', 'macro_bull', 'trend_bull', 'trend_bear']],
    on='timestamp',
    direction='backward'
)

print("\n=== TRADE PERFORMANCE BY MACRO TREND ALIGNMENT ===")
# Trade aligned with macro: LONG when macro_bull, SHORT when not macro_bull
df_merged['aligned'] = ((df_merged['side'] == 'LONG') & df_merged['macro_bull']) | \
                       ((df_merged['side'] == 'SHORT') & (~df_merged['macro_bull']))

print("\n--- ALIGNED VS COUNTER-TREND TRADES ---")
align_grp = df_merged.groupby('aligned').agg(
    count=('net_pnl', 'count'),
    total_pnl=('net_pnl', 'sum'),
    avg_pnl=('net_pnl', 'mean'),
    win_rate=('net_pnl', lambda x: (x > 0).mean() * 100),
    avg_win=('net_pnl', lambda x: x[x > 0].mean()),
    avg_loss=('net_pnl', lambda x: x[x <= 0].mean())
).reset_index()
print(align_grp.to_string(index=False))

print("\n--- SIDE x MACRO_BULL MATRIX ---")
matrix_grp = df_merged.groupby(['macro_bull', 'side']).agg(
    count=('net_pnl', 'count'),
    total_pnl=('net_pnl', 'sum'),
    avg_pnl=('net_pnl', 'mean'),
    win_rate=('net_pnl', lambda x: (x > 0).mean() * 100)
).reset_index()
print(matrix_grp.to_string(index=False))

print("\n--- STRICT TREND (trend_bull / trend_bear / chop) ---")
df_merged['regime_state'] = np.where(df_merged['trend_bull'], 'BULL_TREND',
                            np.where(df_merged['trend_bear'], 'BEAR_TREND', 'CHOP'))

strict_grp = df_merged.groupby(['regime_state', 'side']).agg(
    count=('net_pnl', 'count'),
    total_pnl=('net_pnl', 'sum'),
    win_rate=('net_pnl', lambda x: (x > 0).mean() * 100)
).reset_index()
print(strict_grp.to_string(index=False))
