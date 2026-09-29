"""Quantitative volatility estimators: Parkinson High-Low, Garman-Klass, RiskMetrics EWMA, and GARCH(1,1)."""

from typing import Tuple
import numpy as np
import pandas as pd


ANNUALIZATION_FACTORS = {
    "15m": 35064.0,  # 365.25 * 96
    "1h": 8766.0,    # 365.25 * 24
    "4h": 2191.5,    # 365.25 * 6
    "1d": 365.25,
}


def calculate_parkinson_volatility(
    df: pd.DataFrame,
    window: int = 24,
    timeframe: str = "1h",
) -> float:
    """
    Computes Parkinson High-Low Volatility (1980):
    sigma = sqrt( (1 / (4 * ln(2) * N)) * sum( (ln(H/L))^2 ) ) * sqrt(AnnualFactor) * 100%
    Informationally ~5x more efficient than close-to-close standard deviation.
    """
    if df is None or len(df) < 2:
        return 0.0

    slice_df = df.iloc[-window:] if len(df) >= window else df
    h = slice_df["high"].replace(0.0, np.nan)
    l = slice_df["low"].replace(0.0, np.nan)

    # Avoid zero or negative values
    hl_ratio = (h / l).replace(0.0, np.nan).dropna()
    hl_ratio = hl_ratio[hl_ratio >= 1.0]

    if len(hl_ratio) == 0:
        return 0.0

    log_hl = np.log(hl_ratio)
    sum_sq = np.sum(log_hl**2)
    n = len(hl_ratio)

    variance_per_period = sum_sq / (4.0 * np.log(2.0) * n)
    annual_factor = ANNUALIZATION_FACTORS.get(timeframe, 8766.0)

    annualized_vol = np.sqrt(variance_per_period * annual_factor) * 100.0
    return float(np.nan_to_num(annualized_vol, nan=0.0))


def calculate_garman_klass_volatility(
    df: pd.DataFrame,
    window: int = 24,
    timeframe: str = "1h",
) -> float:
    """
    Computes Garman-Klass Volatility (1980):
    Extends Parkinson by incorporating opening jumps and closing trends.
    ~8x more efficient than standard deviation.
    """
    if df is None or len(df) < 2:
        return 0.0

    slice_df = df.iloc[-window:] if len(df) >= window else df
    o = slice_df["open"].replace(0.0, np.nan)
    h = slice_df["high"].replace(0.0, np.nan)
    l = slice_df["low"].replace(0.0, np.nan)
    c = slice_df["close"].replace(0.0, np.nan)

    hl_ratio = (h / l).clip(lower=1.0)
    co_ratio = (c / o).replace(0.0, np.nan)

    log_hl_sq = (np.log(hl_ratio))**2
    log_co_sq = (np.log(co_ratio))**2

    # Garman-Klass formula
    gk_terms = 0.5 * log_hl_sq - (2.0 * np.log(2.0) - 1.0) * log_co_sq
    variance_per_period = float(gk_terms.mean())

    if variance_per_period < 0.0 or np.isnan(variance_per_period):
        return calculate_parkinson_volatility(df, window, timeframe)

    annual_factor = ANNUALIZATION_FACTORS.get(timeframe, 8766.0)
    annualized_vol = np.sqrt(variance_per_period * annual_factor) * 100.0
    return float(np.nan_to_num(annualized_vol, nan=0.0))


def calculate_ewma_volatility(
    log_returns: pd.Series,
    lambda_param: float = 0.94,
    timeframe: str = "1h",
) -> float:
    """
    Computes J.P. Morgan RiskMetrics Exponentially Weighted Moving Average (EWMA) volatility.
    sigma_t^2 = lambda * sigma_{t-1}^2 + (1 - lambda) * r_{t-1}^2
    """
    if log_returns is None or len(log_returns) < 2:
        return 0.0

    r = log_returns.dropna().values
    if len(r) == 0:
        return 0.0

    # Recursive EWMA variance
    var = r[0]**2
    for t in range(1, len(r)):
        var = lambda_param * var + (1.0 - lambda_param) * (r[t]**2)

    annual_factor = ANNUALIZATION_FACTORS.get(timeframe, 8766.0)
    annualized_vol = np.sqrt(var * annual_factor) * 100.0
    return float(np.nan_to_num(annualized_vol, nan=0.0))


def _fit_garch_params(log_returns: np.ndarray) -> Tuple[float, float]:
    """Simple GARCH(1,1) parameter estimation via grid search on persistence parameters."""
    if len(log_returns) < 30:
        return 0.08, 0.89  # Fallback to calibrated defaults

    r = log_returns[-100:] if len(log_returns) > 100 else log_returns

    best_ll = -np.inf
    best_alpha, best_beta = 0.08, 0.89

    var_sample = float(np.var(r))
    if var_sample <= 0:
        return 0.08, 0.89

    for alpha in np.arange(0.04, 0.20, 0.04):
        for beta in np.arange(0.75, 0.95, 0.04):
            if alpha + beta >= 1.0:
                continue
            omega = var_sample * (1.0 - alpha - beta)
            if omega <= 0:
                continue

            var_t = var_sample
            ll = 0.0
            for t in range(1, len(r)):
                var_t = omega + alpha * (r[t - 1] ** 2) + beta * var_t
                if var_t <= 0 or np.isnan(var_t):
                    ll = -np.inf
                    break
                ll += -0.5 * (np.log(var_t) + (r[t] ** 2) / var_t)

            if ll > best_ll:
                best_ll = ll
                best_alpha, best_beta = float(alpha), float(beta)

    return round(best_alpha, 4), round(best_beta, 4)


def forecast_garch_volatility(
    log_returns: pd.Series,
    horizon_steps: int = 24,
    timeframe: str = "1h",
) -> float:
    """
    Forecasts conditional volatility over horizon_steps forward using GARCH(1,1) dynamics.
    sigma_{t+h}^2 = V_L + (alpha + beta)^h * (sigma_t^2 - V_L)
    Fits GARCH parameters via MLE optimization with fallback to calibrated crypto defaults.
    """
    if log_returns is None or len(log_returns) < 10:
        return calculate_ewma_volatility(log_returns, timeframe=timeframe)

    r = log_returns.dropna().values
    current_ewma_vol = calculate_ewma_volatility(log_returns, lambda_param=0.94, timeframe=timeframe)
    annual_factor = ANNUALIZATION_FACTORS.get(timeframe, 8766.0)

    current_var_per_period = ((current_ewma_vol / 100.0)**2) / annual_factor

    # Fit GARCH(1,1) parameters to empirical return series
    alpha, beta = _fit_garch_params(r)
    persistence = alpha + beta

    if persistence < 1.0:
        omega = float(np.var(r)) * (1.0 - persistence)
        long_run_var = omega / max(1e-10, 1.0 - persistence)
    else:
        long_run_var = float(np.var(r)) if len(r) > 1 else 0.0001

    # Average expected variance over the horizon
    forward_vars = []
    for h in range(1, horizon_steps + 1):
        sigma_sq_h = long_run_var + (persistence**h) * (current_var_per_period - long_run_var)
        forward_vars.append(max(1e-8, sigma_sq_h))

    avg_forward_var = float(np.mean(forward_vars))
    annualized_forecast = np.sqrt(avg_forward_var * annual_factor) * 100.0
    return float(np.nan_to_num(annualized_forecast, nan=current_ewma_vol))

