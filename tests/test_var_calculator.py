"""Unit tests for VaRCalculator (Sprint 7)."""

import numpy as np
import pytest
from models.var_calculator import VaRCalculator


@pytest.fixture
def normal_returns():
    """Generates standard Gaussian returns."""
    np.random.seed(42)
    return np.random.normal(loc=0.0005, scale=0.015, size=500)


@pytest.fixture
def fat_tailed_returns():
    """Generates Student-t fat-tailed returns with high kurtosis."""
    np.random.seed(42)
    # Student-t with df=4 has excess kurtosis, generates fat tails
    return np.random.standard_t(df=4, size=500) * 0.015


def test_moments_computation(normal_returns):
    mean, std, skew, kurt = VaRCalculator.compute_moments(normal_returns)
    assert abs(mean - 0.0005) < 0.005
    assert abs(std - 0.015) < 0.005
    assert abs(skew) < 0.5  # Normal is symmetric
    assert abs(kurt) < 0.8  # Normal has 0 excess kurtosis


def test_parametric_var(normal_returns):
    var_95 = VaRCalculator.compute_parametric_var(normal_returns, confidence_level=0.95, horizon_bars=96)
    assert var_95 > 0.0
    # 96 bars scaling = sqrt(96) ~= 9.79. std ~0.015 * 1.645 * 9.79 ~= 0.24 (24% daily VaR)
    assert 0.10 < var_95 < 0.40


def test_historical_var(normal_returns):
    var_hist = VaRCalculator.compute_historical_var(normal_returns, confidence_level=0.95, horizon_bars=96)
    assert var_hist > 0.0
    assert 0.10 < var_hist < 0.40


def test_cornish_fisher_with_fat_tails(fat_tailed_returns):
    mean, std, skew, kurt = VaRCalculator.compute_moments(fat_tailed_returns)
    cf_var = VaRCalculator.compute_cornish_fisher_var(fat_tailed_returns, confidence_level=0.95, horizon_bars=96)
    param_var = VaRCalculator.compute_parametric_var(fat_tailed_returns, confidence_level=0.95, horizon_bars=96)

    assert cf_var > 0.0
    # For fat tails, Cornish-Fisher should typically project higher or equal risk than standard Gaussian
    assert cf_var >= param_var * 0.90


def test_domain_of_monotonicity_fallback():
    """When excess kurtosis is extreme (> 6.0), CF must safely fall back to Historical VaR."""
    # Construct an extreme outlier dataset
    extreme_returns = np.array([0.001] * 200 + [-0.35, -0.25, 0.40])
    _, _, skew, kurt = VaRCalculator.compute_moments(extreme_returns)
    assert kurt > 6.0  # Extreme excess kurtosis

    # Should not throw exception and should match historical VaR
    cf_var = VaRCalculator.compute_cornish_fisher_var(extreme_returns, confidence_level=0.95, horizon_bars=1)
    hist_var = VaRCalculator.compute_historical_var(extreme_returns, confidence_level=0.95, horizon_bars=1)
    assert cf_var == hist_var


def test_cvar_greater_than_or_equal_to_var(normal_returns):
    """Sub-additivity / coherence: Expected Shortfall (CVaR) must always be >= VaR."""
    var_cf = VaRCalculator.compute_cornish_fisher_var(normal_returns, confidence_level=0.95, horizon_bars=96)
    cvar = VaRCalculator.compute_cvar_expected_shortfall(normal_returns, confidence_level=0.95, horizon_bars=96)

    assert cvar >= var_cf


def test_risk_summary_structure(normal_returns):
    summary = VaRCalculator.compute_risk_summary(normal_returns, portfolio_equity=10000.0)
    assert "parametric_var_95_pct" in summary
    assert "historical_var_95_pct" in summary
    assert "cornish_fisher_var_95_pct" in summary
    assert "cvar_expected_shortfall_95_pct" in summary
    assert "var_95_1day_usd" in summary
    assert "cvar_95_1day_usd" in summary
    assert summary["var_95_1day_usd"] > 0.0
    assert summary["cvar_95_1day_usd"] >= summary["var_95_1day_usd"]


def test_empty_and_degenerate_returns():
    empty_var = VaRCalculator.compute_parametric_var(np.array([]))
    assert empty_var > 0.0  # Conservative fallback

    zeros_var = VaRCalculator.compute_parametric_var(np.zeros(50))
    assert zeros_var == 0.0
