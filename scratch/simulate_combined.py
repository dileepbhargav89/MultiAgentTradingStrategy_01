import json
import pandas as pd
import numpy as np

with open('data/backtest_results_2y_v2.json') as f:
    data = json.load(f)

trades = data.get('trade_history', [])
df_t = pd.DataFrame(trades)
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

# 1. Macro Trend Aligned trades
df_aligned = df_merged[
    ((df_merged['side'] == 'LONG') & df_merged['macro_bull']) |
    ((df_merged['side'] == 'SHORT') & (~df_merged['macro_bull']))
].copy()

# 2. Rescale notional if notional > $1,500 (15% max notional cap)
cap_usd = 1500.0
df_aligned['notional'] = df_aligned['quantity'] * df_aligned['entry_price']
df_aligned['scale'] = np.where(df_aligned['notional'] > cap_usd, cap_usd / df_aligned['notional'], 1.0)
df_aligned['scaled_pnl'] = df_aligned['net_pnl'] * df_aligned['scale']

initial_capital = 10000.0
df_aligned['cum_pnl'] = df_aligned['scaled_pnl'].cumsum()
df_aligned['equity'] = initial_capital + df_aligned['cum_pnl']
df_aligned['hwm'] = df_aligned['equity'].cummax()
df_aligned['drawdown'] = (df_aligned['hwm'] - df_aligned['equity']) / df_aligned['hwm']

wins = df_aligned[df_aligned['scaled_pnl'] > 0]
losses = df_aligned[df_aligned['scaled_pnl'] <= 0]
win_rate = len(wins) / len(df_aligned) * 100
total_return_pct = (df_aligned['equity'].iloc[-1] / initial_capital - 1) * 100
max_dd_pct = df_aligned['drawdown'].max() * 100
avg_win = wins['scaled_pnl'].mean()
avg_loss = losses['scaled_pnl'].mean()
gross_profit = wins['scaled_pnl'].sum()
gross_loss = abs(losses['scaled_pnl'].sum())
pf = gross_profit / gross_loss if gross_loss > 0 else 0

# Compute Sharpe & Sortino
returns = df_aligned['scaled_pnl'] / initial_capital
sharpe = np.sqrt(365 * 24 / 4) * (returns.mean() / returns.std()) if returns.std() > 0 else 0
downside = returns[returns < 0]
sortino = np.sqrt(365 * 24 / 4) * (returns.mean() / downside.std()) if len(downside) > 0 and downside.std() > 0 else 0

print("=================================================================")
print("   SIMULATION: MACRO TREND ALIGNED + 15% MAX NOTIONAL CAP")
print("=================================================================")
print(f"Total Trades: {len(df_aligned)}")
print(f"Total Net PnL: ${df_aligned['cum_pnl'].iloc[-1]:,.2f}")
print(f"Final Equity: ${df_aligned['equity'].iloc[-1]:,.2f}")
print(f"Total Return: {total_return_pct:+.2f}%")
print(f"Win Rate: {win_rate:.1f}% ({len(wins)} wins / {len(losses)} losses)")
print(f"Profit Factor: {pf:.2f}")
print(f"Max Drawdown: {max_dd_pct:.2f}%")
print(f"Annualized Sharpe Estimate: {sharpe:.2f}")
print(f"Annualized Sortino Estimate: {sortino:.2f}")
print(f"Avg Win: ${avg_win:,.2f} | Avg Loss: ${avg_loss:,.2f}")
print(f"Payoff Ratio: {abs(avg_win / avg_loss):.2f}:1")
