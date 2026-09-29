import json
import pandas as pd
import numpy as np

with open('data/backtest_results_2y_v2.json') as f:
    data = json.load(f)

trades = data.get('trade_history', [])
print(f"Total trades: {len(trades)}")

if not trades:
    print("No trades found in trade_history!")
    exit()

df = pd.DataFrame(trades)
pnl_col = 'net_pnl'

# 1. PnL Stats
total_pnl = df[pnl_col].sum()
wins = df[df[pnl_col] > 0]
losses = df[df[pnl_col] <= 0]
win_rate = len(wins) / len(df) * 100
avg_win = wins[pnl_col].mean() if len(wins) > 0 else 0
avg_loss = losses[pnl_col].mean() if len(losses) > 0 else 0
payoff = abs(avg_win / avg_loss) if avg_loss != 0 else 0
gross_profit = wins[pnl_col].sum()
gross_loss = abs(losses[pnl_col].sum())
pf = gross_profit / gross_loss if gross_loss != 0 else 0

print(f"\n--- OVERALL METRICS ---")
print(f"Total Net PnL: ${total_pnl:,.2f}")
print(f"Win Rate: {win_rate:.1f}% ({len(wins)} wins / {len(losses)} losses)")
print(f"Avg Win: ${avg_win:,.2f} | Avg Loss: ${avg_loss:,.2f}")
print(f"Payoff Ratio (Avg Win / Avg Loss): {payoff:.2f}:1")
print(f"Profit Factor: {pf:.2f}")

# 2. Exit Reason Breakdown
if 'exit_reason' in df.columns:
    print(f"\n--- EXIT REASONS ---")
    exit_grp = df.groupby('exit_reason').agg(
        count=(pnl_col, 'count'),
        total_pnl=(pnl_col, 'sum'),
        avg_pnl=(pnl_col, 'mean'),
        win_rate=(pnl_col, lambda x: (x > 0).mean() * 100)
    ).reset_index()
    print(exit_grp.to_string(index=False))

# 3. Side Breakdown (LONG vs SHORT)
if 'side' in df.columns:
    print(f"\n--- SIDE PERFORMANCE (LONG vs SHORT) ---")
    side_grp = df.groupby('side').agg(
        count=(pnl_col, 'count'),
        total_pnl=(pnl_col, 'sum'),
        avg_pnl=(pnl_col, 'mean'),
        win_rate=(pnl_col, lambda x: (x > 0).mean() * 100)
    ).reset_index()
    print(side_grp.to_string(index=False))

# 4. Position Size (Notional) Quintiles
if 'quantity' in df.columns and 'entry_price' in df.columns:
    df['notional'] = df['quantity'] * df['entry_price']
    df['notional_q'] = pd.qcut(df['notional'], q=5, duplicates='drop')
    print(f"\n--- PERFORMANCE BY NOTIONAL QUINTILE ---")
    q_grp = df.groupby('notional_q', observed=False).agg(
        count=(pnl_col, 'count'),
        total_pnl=(pnl_col, 'sum'),
        avg_pnl=(pnl_col, 'mean'),
        win_rate=(pnl_col, lambda x: (x > 0).mean() * 100)
    ).reset_index()
    print(q_grp.to_string(index=False))

# 5. Return Pct Analysis
if 'return_pct' in df.columns:
    print(f"\n--- RETURN PCT DISTRIBUTION ---")
    print(f"Avg return % on wins: {wins['return_pct'].mean():.2f}%")
    print(f"Avg return % on losses: {losses['return_pct'].mean():.2f}%")
    print(f"Median win %: {wins['return_pct'].median():.2f}%")
    print(f"Median loss %: {losses['return_pct'].median():.2f}%")

# 6. Parse notes for extra context if available
if 'notes' in df.columns:
    print(f"\n--- SAMPLE NOTES ---")
    print(df['notes'].value_counts().head(10))

# 7. Consecutive losses distribution
if 'consecutive_losses' in df.columns:
    print(f"\nMax consecutive losses observed: {df['consecutive_losses'].max()}")
    print("Consecutive losses counts:")
    print(df['consecutive_losses'].value_counts().sort_index())
