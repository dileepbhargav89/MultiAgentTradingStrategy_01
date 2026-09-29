"""Quantitative Kelly Criterion and Volatility-Targeted Position Sizing Engine.

Implements Full Kelly, Half-Kelly (0.50), Quarter-Kelly (0.25), Inverse-ATR
volatility parity sizing, and institutional dollar-risk cap enforcement.
"""

from typing import Any, Dict, Optional, Tuple
import numpy as np
from loguru import logger


class KellySizingEngine:
    """Computes mathematically optimal position sizing via Fractional Kelly and Volatility Parity."""

    @staticmethod
    def compute_full_kelly(win_rate: float, win_loss_ratio: float) -> float:
        """Computes unleveraged Full Kelly fraction.

        Formula:
            f* = (p * b - q) / b
        where:
            p = win_rate
            q = 1 - win_rate
            b = win_loss_ratio (avg_win / avg_loss)
        """
        p = float(win_rate)
        b = float(win_loss_ratio)

        if p <= 0.0 or b <= 0.0:
            return 0.0

        q = 1.0 - p
        edge = p * b - q
        if edge <= 0.0:
            return 0.0

        f_star = edge / b
        return float(min(1.0, max(0.0, f_star)))

    @classmethod
    def compute_fractional_kelly(
        cls,
        win_rate: float,
        win_loss_ratio: float,
        fraction: float = 0.50,
    ) -> float:
        """Computes Fractional Kelly fraction (default 0.50 for Half-Kelly).

        Formula:
            f_fractional = fraction * f*
        """
        full_k = cls.compute_full_kelly(win_rate, win_loss_ratio)
        return float(min(1.0, max(0.0, full_k * fraction)))

    @classmethod
    def compute_volatility_parity_size(
        cls,
        target_risk_usd: float,
        entry_price: float,
        stop_loss_price: float,
    ) -> Tuple[float, float, float]:
        """Calculates position size strictly bounded by a targeted dollar risk at the stop level.

        Returns:
            (position_size_usd, position_size_asset, stop_distance_pct)
        """
        if entry_price <= 0.0 or stop_loss_price <= 0.0 or target_risk_usd <= 0.0:
            return 0.0, 0.0, 0.0

        stop_dist_pct = abs(entry_price - stop_loss_price) / entry_price
        if stop_dist_pct < 1e-6:
            return 0.0, 0.0, 0.0

        # Position Size USD = Dollar Risk / Stop Distance %
        size_usd = target_risk_usd / stop_dist_pct
        size_asset = size_usd / entry_price

        return float(size_usd), float(size_asset), float(stop_dist_pct)

    @classmethod
    def compute_composite_size(
        cls,
        portfolio_equity: float,
        win_rate: float,
        win_loss_ratio: float,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        risk_tier_multiplier: float = 1.0,
        volatility_multiplier: float = 1.0,
        crowding_penalty: float = 0.0,
        kelly_fraction: float = 0.50,
        max_dollar_risk_pct: float = 0.015,  # 1.5% max risk cap
        min_order_usd: float = 15.0,         # Binance min notional buffer
        round_trip_fee_pct: float = 0.0010,  # 0.10% taker + slip
        min_fee_drag_ratio: float = 3.0,     # Profit / Fee >= 3x
        max_position_equity_pct: float = 0.50, # 50% max notional cap
        use_risk_budget_sizing: bool = False,  # Size from stop-distance risk budget
    ) -> Dict[str, Any]:
        """Synthesizes Half-Kelly edge, inverse volatility distance, and institutional constraints."""
        if portfolio_equity <= 0.0 or entry_price <= 0.0 or stop_loss_price <= 0.0:
            return {
                "approved": False,
                "rejection_reason": "INVALID_PORTFOLIO_OR_PRICE_PARAMETERS",
                "position_size_usd": 0.0,
                "position_size_asset": 0.0,
                "dollar_risk_usd": 0.0,
                "dollar_risk_pct": 0.0,
                "fee_drag_ratio": 0.0,
            }

        stop_dist_pct = abs(entry_price - stop_loss_price) / entry_price
        if stop_dist_pct < 0.002 or stop_dist_pct > 0.08:
            return {
                "approved": False,
                "rejection_reason": f"STOP_DISTANCE_OUT_OF_BOUNDS ({stop_dist_pct*100:.2f}%)",
                "position_size_usd": 0.0,
                "position_size_asset": 0.0,
                "dollar_risk_usd": 0.0,
                "dollar_risk_pct": 0.0,
                "fee_drag_ratio": 0.0,
            }

        # 1. Kelly Sizing
        full_k = cls.compute_full_kelly(win_rate, win_loss_ratio)
        frac_k = cls.compute_fractional_kelly(win_rate, win_loss_ratio, fraction=kelly_fraction)

        if frac_k <= 0.0:
            return {
                "approved": False,
                "rejection_reason": f"NEGATIVE_OR_ZERO_KELLY_EDGE (Full Kelly={full_k:.1%})",
                "position_size_usd": 0.0,
                "position_size_asset": 0.0,
                "dollar_risk_usd": 0.0,
                "dollar_risk_pct": 0.0,
                "fee_drag_ratio": 0.0,
            }

        # 2. Raw Position Size from Kelly
        if use_risk_budget_sizing:
            # Scale dollar risk budget proportionally with Kelly edge (target 0.15 for full risk)
            risk_edge_scalar = float(np.clip(frac_k / 0.15, 0.20, 1.0))
            effective_risk_pct = max_dollar_risk_pct * risk_edge_scalar
            target_risk_usd = portfolio_equity * effective_risk_pct
            raw_size_usd = target_risk_usd / max(1e-4, stop_dist_pct)
        else:
            raw_size_usd = portfolio_equity * frac_k

        # 3. Multiplier Adjustments (Risk Tier * Volatility Multiplier * Crowding Dampener)
        crowding_dampener = max(0.0, 1.0 - crowding_penalty)
        adjusted_size_usd = (
            raw_size_usd
            * risk_tier_multiplier
            * volatility_multiplier
            * crowding_dampener
        )

        # Cap single-position notional exposure
        max_notional_cap = portfolio_equity * max_position_equity_pct
        adjusted_size_usd = min(adjusted_size_usd, max_notional_cap)

        # 4. Enforce Hard Dollar Risk Cap (R <= 1.5% of Equity)
        max_dollar_risk = portfolio_equity * max_dollar_risk_pct
        current_dollar_risk = adjusted_size_usd * stop_dist_pct

        if current_dollar_risk > max_dollar_risk:
            # Downscale position size so dollar loss at stop == max_dollar_risk exactly
            adjusted_size_usd = max_dollar_risk / stop_dist_pct
            current_dollar_risk = max_dollar_risk

        # 5. Check Minimum Notional Size
        if adjusted_size_usd < min_order_usd:
            return {
                "approved": False,
                "rejection_reason": f"POSITION_SIZE_BELOW_MIN_NOTIONAL (${adjusted_size_usd:.2f} < ${min_order_usd:.2f})",
                "position_size_usd": 0.0,
                "position_size_asset": 0.0,
                "dollar_risk_usd": 0.0,
                "dollar_risk_pct": 0.0,
                "fee_drag_ratio": 0.0,
            }

        # 6. Fee Efficiency Hurdle
        reward_dist_pct = abs(take_profit_price - entry_price) / entry_price
        expected_profit_usd = adjusted_size_usd * reward_dist_pct
        round_trip_fee_usd = adjusted_size_usd * round_trip_fee_pct
        fee_drag_ratio = expected_profit_usd / max(1e-4, round_trip_fee_usd)

        if fee_drag_ratio < min_fee_drag_ratio:
            return {
                "approved": False,
                "rejection_reason": f"EXCESSIVE_FEE_DRAG (Profit/Fee={fee_drag_ratio:.1f}x < {min_fee_drag_ratio:.1f}x)",
                "position_size_usd": 0.0,
                "position_size_asset": 0.0,
                "dollar_risk_usd": 0.0,
                "dollar_risk_pct": 0.0,
                "fee_drag_ratio": fee_drag_ratio,
            }

        position_size_asset = adjusted_size_usd / entry_price
        final_risk_pct = current_dollar_risk / portfolio_equity

        return {
            "approved": True,
            "rejection_reason": None,
            "full_kelly_pct": full_k,
            "fractional_kelly_pct": frac_k,
            "position_size_usd": adjusted_size_usd,
            "position_size_asset": position_size_asset,
            "dollar_risk_usd": current_dollar_risk,
            "dollar_risk_pct": final_risk_pct,
            "fee_estimate_usd": round_trip_fee_usd,
            "fee_drag_ratio": fee_drag_ratio,
            "stop_dist_pct": stop_dist_pct,
            "reward_dist_pct": reward_dist_pct,
        }
