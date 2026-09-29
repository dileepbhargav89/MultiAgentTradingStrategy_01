import json
import pandas as pd
import numpy as np

data = json.load(open('data/backtest_results_2y_v2.json'))
trades = data.get('trade_history', [])
print(f"Total trades: {len(trades)}")

gross_pnls = [t.get('gross_pnl', 0.0) for t in trades]
net_pnls = [t.get('net_pnl', 0.0) for t in trades]
fees = [t.get('gross_pnl', 0.0) - t.get('net_pnl', 0.0) for t in trades]

print(f"Sum Gross PnL: ${sum(gross_pnls):.2f}")
print(f"Sum Net PnL:   ${sum(net_pnls):.2f}")
print(f"Total Fees:    ${sum(fees):.2f}")

quantities = [t.get('quantity', 0.0) for t in trades]
entry_prices = [t.get('entry_price', 0.0) for t in trades]
notionals = [q * p for q, p in zip(quantities, entry_prices)]

print(f"Avg Notional Position: ${sum(notionals)/len(notionals):.2f}")
print(f"Min Notional: ${min(notionals):.2f} | Max Notional: ${max(notionals):.2f}")

wins = [p for p in net_pnls if p > 0]
losses = [p for p in net_pnls if p < 0]

print(f"Wins count: {len(wins)} | Losses count: {len(losses)}")
print(f"Total Win PnL: ${sum(wins):.2f} | Total Loss PnL: ${sum(losses):.2f}")
print(f"Avg Win PnL:   ${np.mean(wins):.2f} | Avg Loss PnL:   ${np.mean(losses):.2f}")
print(f"Payoff Ratio:  {abs(np.mean(wins)/np.mean(losses)):.2f}")

# Long vs Short
long_trades = [t for t in trades if t.get('side') == 'LONG']
short_trades = [t for t in trades if t.get('side') == 'SHORT']
print(f"\nLong trades: {len(long_trades)}")
print(f"Long Gross PnL: ${sum(t.get('gross_pnl', 0) for t in long_trades):.2f}")
print(f"Long Net PnL:   ${sum(t.get('net_pnl', 0) for t in long_trades):.2f}")
print(f"Long Win Rate:  {sum(1 for t in long_trades if t.get('net_pnl', 0) > 0)/len(long_trades)*100:.1f}%")

print(f"\nShort trades: {len(short_trades)}")
print(f"Short Gross PnL: ${sum(t.get('gross_pnl', 0) for t in short_trades):.2f}")
print(f"Short Net PnL:   ${sum(t.get('net_pnl', 0) for t in short_trades):.2f}")
print(f"Short Win Rate:  {sum(1 for t in short_trades if t.get('net_pnl', 0) > 0)/len(short_trades)*100:.1f}%")

# Exit reasons
exit_reasons = {}
for t in trades:
    r = t.get('exit_reason', 'UNKNOWN')
    exit_reasons[r] = exit_reasons.get(r, 0) + 1
print(f"\nExit reasons: {exit_reasons}")

# Trade return percentages
ret_pcts = [t.get('return_pct', 0.0) for t in trades]
print(f"Avg trade return: {np.mean(ret_pcts):.2f}%")
print(f"Max trade gain:   +{max(ret_pcts):.2f}%")
print(f"Max trade loss:   {min(ret_pcts):.2f}%")
