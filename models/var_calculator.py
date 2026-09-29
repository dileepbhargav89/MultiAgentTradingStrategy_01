"""Quantitative Value at Risk (VaR) and Expected Shortfall (CVaR) Calculator.

Implements Parametric, Non-Parametric (Historical), and Cornish-Fisher leptokurtic
adjustments with domain-of-monotonicity safeguards and sub-additive Expected Shortfall.
"""

from typing import Any, Dict, Optional, Tuple
import numpy as np
from scipy import stats
from loguru import logger


class VaRCalculator:
    """Calculates Parametric, Historical, and Cornish-Fisher VaR & CVaR for portfolio return series."""

    @staticmethod
    def _clean_returns(returns: np.ndarray) -> np.ndarray:
        """Sanitizes returns array, removing NaNs, Infs, and flattening."""
        if returns is None or len(returns) == 0:
            return np.array([], dtype=float)
        arr = np.asarray(returns, dtype=float).ravel()
        arr = arr[np.isfinite(arr)]
        return arr

    @classmethod
    def compute_moments(cls, returns: np.ndarray) -> Tuple[float, float, float, float]:
        """Computes mean, standard deviation, skewness, and Fisher excess kurtosis.

        Returns:
            (mean, std, skewness, excess_kurtosis)
        """
        arr = cls._clean_returns(returns)
        if len(arr) < 5:
            return 0.0, 0.0, 0.0, 0.0

        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1))
        if std < 1e-12:
            return mean, 0.0, 0.0, 0.0

        skewness = float(stats.skew(arr, bias=False))
        # stats.kurtosis computes Fisher excess kurtosis (normal = 0.0)
        excess_kurtosis = float(stats.kurtosis(arr, fisher=True, bias=False))

        return mean, std, skewness, excess_kurtosis

    @classmethod
    def compute_parametric_var(
        cls,
        returns: np.ndarray,
        confidence_level: float = 0.95,
        horizon_bars: int = 96,
    ) -> float:
        """Computes Gaussian Parametric Value at Risk (expressed as a positive loss fraction).

        Formula:
            VaR = max(0, Z_alpha * sigma * sqrt(T) - mu * T)
        """
        arr = cls._clean_returns(returns)
        if len(arr) < 10:
            return 0.04  # Default 4% fallback if insufficient data

        mean, std, _, _ = cls.compute_moments(arr)
        if std < 1e-12:
            return 0.0

        z_alpha = float(stats.norm.ppf(confidence_level))
        scale = np.sqrt(max(1, horizon_bars))
        var = z_alpha * std * scale - mean * horizon_bars
        return float(max(0.0, var))

    @classmethod
    def compute_historical_var(
        cls,
        returns: np.ndarray,
        confidence_level: float = 0.95,
        horizon_bars: int = 96,
    ) -> float:
        """Computes Non-Parametric Empirical Quantile Value at Risk.

        Formula:
            q_alpha = quantile(returns, 1 - confidence_level)
            VaR = -min(0, q_alpha) * sqrt(T)
        """
        arr = cls._clean_returns(returns)
        if len(arr) < 10:
            return 0.04

        alpha = 1.0 - confidence_level
        q_alpha = float(np.quantile(arr, alpha))
        scale = np.sqrt(max(1, horizon_bars))
        var = -min(0.0, q_alpha) * scale
        return float(max(0.0, var))

    @classmethod
    def compute_cornish_fisher_var(
        cls,
        returns: np.ndarray,
        confidence_level: float = 0.95,
        horizon_bars: int = 96,
    ) -> float:
        """Computes Cornish-Fisher expansion Value at Risk, adjusting for skewness & fat tails.

        Formula:
            z_tilde = z + (z^2 - 1)*gamma_3/6 + (z^3 - 3z)*kappa/24 - (2z^3 - 5z)*gamma_3^2/36
            VaR_CF = max(0, z_tilde * sigma * sqrt(T) - mu * T)

        Domain of Monotonicity Safeguard:
            If excess kurtosis > 6.0 or |skewness| > 2.0 or z_tilde <= 0, the expansion
            polynomial inverts and becomes invalid. In this scenario, it automatically
            falls back to Historical Simulation VaR.
        """
        arr = cls._clean_returns(returns)
        if len(arr) < 15:
            return cls.compute_parametric_var(arr, confidence_level, horizon_bars)

        mean, std, skewness, excess_kurt = cls.compute_moments(arr)
        if std < 1e-12:
            return 0.0

        # Check domain of monotonicity
        if abs(skewness) > 2.0 or excess_kurt > 6.0:
            logger.debug(
                f"Cornish-Fisher out of monotonicity domain (skew={skewness:.2f}, kurt={excess_kurt:.2f}). "
                "Falling back to Historical VaR."
            )
            return cls.compute_historical_var(arr, confidence_level, horizon_bars)

        z = float(stats.norm.ppf(confidence_level))
        g1 = skewness
        g2 = excess_kurt

        # Cornish-Fisher polynomial expansion
        z_tilde = (
            z
            + (z**2 - 1.0) * g1 / 6.0
            + (z**3 - 3.0 * z) * g2 / 24.0
            - (2.0 * z**3 - 5.0 * z) * (g1**2) / 36.0
        )

        # Monotonicity sanity check: z_tilde must remain positive and sensible
        if z_tilde <= 0.0 or z_tilde > 5.0:
            return cls.compute_historical_var(arr, confidence_level, horizon_bars)

        scale = np.sqrt(max(1, horizon_bars))
        var_cf = z_tilde * std * scale - mean * horizon_bars
        return float(max(0.0, var_cf))

    @classmethod
    def compute_cvar_expected_shortfall(
        cls,
        returns: np.ndarray,
        confidence_level: float = 0.95,
        horizon_bars: int = 96,
    ) -> float:
        """Computes Conditional Value at Risk (Expected Shortfall).

        Formula:
            CVaR = -E[ R | R <= q_alpha ] * sqrt(T)
        Guaranteed to satisfy CVaR >= VaR (coherent risk measure property).
        """
        arr = cls._clean_returns(returns)
        if len(arr) < 10:
            return 0.055

        alpha = 1.0 - confidence_level
        q_alpha = float(np.quantile(arr, alpha))
        scale = np.sqrt(max(1, horizon_bars))

        tail = arr[arr <= q_alpha]
        if len(tail) >= 3:
            tail_mean = float(np.mean(tail))
            cvar = -min(0.0, tail_mean) * scale
        else:
            # Parametric normal/Student-t tail expectation fallback
            var_base = cls.compute_parametric_var(arr, confidence_level, horizon_bars)
            z = stats.norm.ppf(confidence_level)
            cvar = var_base * (stats.norm.pdf(z) / (alpha * z))

        # Enforce mathematical coherence: CVaR must be >= VaR
        cf_var = cls.compute_cornish_fisher_var(arr, confidence_level, horizon_bars)
        return float(max(cvar, cf_var))

    @classmethod
    def compute_risk_summary(
        cls,
        returns: np.ndarray,
        portfolio_equity: float,
        confidence_level: float = 0.95,
        horizon_bars: Optional[int] = None,
        timeframe: str = "1h",
    ) -> Dict[str, Any]:
        """Computes full quantitative risk report including VaR/CVaR in % and USD."""
        if horizon_bars is None:
            horizon_map = {"15m": 96, "1h": 24, "4h": 6, "1d": 1}
            horizon_bars = horizon_map.get(timeframe, 24)

        arr = cls._clean_returns(returns)
        mean, std, skew, kurt = cls.compute_moments(arr)

        param_var = cls.compute_parametric_var(arr, confidence_level, horizon_bars)
        hist_var = cls.compute_historical_var(arr, confidence_level, horizon_bars)
        cf_var = cls.compute_cornish_fisher_var(arr, confidence_level, horizon_bars)
        cvar = cls.compute_cvar_expected_shortfall(arr, confidence_level, horizon_bars)

        # Selected primary institutional metric is Cornish-Fisher VaR (or fallback)
        primary_var_pct = cf_var
        primary_cvar_pct = cvar

        var_usd = primary_var_pct * portfolio_equity
        cvar_usd = primary_cvar_pct * portfolio_equity

        return {
            "mean_return": round(mean, 6),
            "volatility_std": round(std, 6),
            "skewness": round(skew, 4),
            "excess_kurtosis": round(kurt, 4),
            "is_leptokurtic": bool(kurt > 0.5 or abs(skew) > 0.5),
            "parametric_var_95_pct": round(param_var, 4),
            "historical_var_95_pct": round(hist_var, 4),
            "cornish_fisher_var_95_pct": round(cf_var, 4),
            "cvar_expected_shortfall_95_pct": round(cvar, 4),
            "var_95_1day_usd": round(var_usd, 2),
            "cvar_95_1day_usd": round(cvar_usd, 2),
        }
