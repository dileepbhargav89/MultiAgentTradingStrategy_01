import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.kelly_sizing import KellySizingEngine

equity = 10000.0
win_rate = 0.55
win_loss_ratio = 1.50
entry_price = 65000.0

# Case A: Tight stop (0.8% stop distance)
stop_price_tight = 65000.0 * (1.0 - 0.008)
tp_price_tight = 65000.0 * (1.0 + 0.016)

# Case B: Standard stop (1.8% stop distance)
stop_price_std = 65000.0 * (1.0 - 0.018)
tp_price_std = 65000.0 * (1.0 + 0.036)

print("--- MODE 1: use_risk_budget_sizing = True (Current) ---")
res_tight = KellySizingEngine.compute_composite_size(
    portfolio_equity=equity,
    win_rate=win_rate,
    win_loss_ratio=win_loss_ratio,
    entry_price=entry_price,
    stop_loss_price=stop_price_tight,
    take_profit_price=tp_price_tight,
    use_risk_budget_sizing=True,
    max_position_equity_pct=0.25,
)
res_std = KellySizingEngine.compute_composite_size(
    portfolio_equity=equity,
    win_rate=win_rate,
    win_loss_ratio=win_loss_ratio,
    entry_price=entry_price,
    stop_loss_price=stop_price_std,
    take_profit_price=tp_price_std,
    use_risk_budget_sizing=True,
    max_position_equity_pct=0.25,
)
print(f"Tight stop size: ${res_tight['position_size_usd']:.2f} | Dollar risk: ${res_tight['dollar_risk_usd']:.2f}")
print(f"Std stop size:   ${res_std['position_size_usd']:.2f} | Dollar risk: ${res_std['dollar_risk_usd']:.2f}")

print("\n--- MODE 2: use_risk_budget_sizing = False (Pure Fractional Kelly) ---")
res_tight2 = KellySizingEngine.compute_composite_size(
    portfolio_equity=equity,
    win_rate=win_rate,
    win_loss_ratio=win_loss_ratio,
    entry_price=entry_price,
    stop_loss_price=stop_price_tight,
    take_profit_price=tp_price_tight,
    use_risk_budget_sizing=False,
    max_position_equity_pct=0.15,
)
res_std2 = KellySizingEngine.compute_composite_size(
    portfolio_equity=equity,
    win_rate=win_rate,
    win_loss_ratio=win_loss_ratio,
    entry_price=entry_price,
    stop_loss_price=stop_price_std,
    take_profit_price=tp_price_std,
    use_risk_budget_sizing=False,
    max_position_equity_pct=0.15,
)
print(f"Tight stop size: ${res_tight2['position_size_usd']:.2f} | Dollar risk: ${res_tight2['dollar_risk_usd']:.2f}")
print(f"Std stop size:   ${res_std2['position_size_usd']:.2f} | Dollar risk: ${res_std2['dollar_risk_usd']:.2f}")
