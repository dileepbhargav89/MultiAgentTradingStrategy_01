"""Unit tests for KellySizingEngine (Sprint 8)."""

import pytest
from models.kelly_sizing import KellySizingEngine


def test_full_kelly_calculation():
    # p = 0.60, b = 2.0 -> (0.6 * 2 - 0.4) / 2 = 0.8 / 2 = 0.40
    fk = KellySizingEngine.compute_full_kelly(win_rate=0.60, win_loss_ratio=2.0)
    assert fk == pytest.approx(0.40, rel=1e-3)

    # Negative edge: p = 0.40, b = 1.0 -> (0.4 - 0.6) / 1 = -0.2 -> 0.0
    fk_neg = KellySizingEngine.compute_full_kelly(win_rate=0.40, win_loss_ratio=1.0)
    assert fk_neg == 0.0


def test_fractional_kelly():
    # Half-Kelly of 0.40 is 0.20
    hk = KellySizingEngine.compute_fractional_kelly(win_rate=0.60, win_loss_ratio=2.0, fraction=0.50)
    assert hk == pytest.approx(0.20, rel=1e-3)

    # Quarter-Kelly of 0.40 is 0.10
    qk = KellySizingEngine.compute_fractional_kelly(win_rate=0.60, win_loss_ratio=2.0, fraction=0.25)
    assert qk == pytest.approx(0.10, rel=1e-3)


def test_volatility_parity_sizing():
    # Dollar risk = $150, Entry = $60,000, Stop = $58,800 (2% distance)
    size_usd, size_asset, dist_pct = KellySizingEngine.compute_volatility_parity_size(
        target_risk_usd=150.0,
        entry_price=60000.0,
        stop_loss_price=58800.0,
    )
    assert dist_pct == pytest.approx(0.02, rel=1e-3)
    assert size_usd == pytest.approx(7500.0, rel=1e-3)
    assert size_asset == pytest.approx(7500.0 / 60000.0, rel=1e-3)


def test_composite_size_dollar_risk_cap_clamping():
    # Equity = $10,000, Stop distance = 2%, Half-Kelly = 0.20 -> Raw size = $2,000
    # Dollar risk at stop = $2,000 * 0.02 = $40 (well within $150 cap)
    res = KellySizingEngine.compute_composite_size(
        portfolio_equity=10000.0,
        win_rate=0.60,
        win_loss_ratio=2.0,
        entry_price=60000.0,
        stop_loss_price=58800.0,      # 2% stop
        take_profit_price=63600.0,    # 6% target -> 3.0 R:R
        kelly_fraction=0.50,
        max_dollar_risk_pct=0.015,
    )
    assert res["approved"] is True
    assert res["position_size_usd"] == pytest.approx(2000.0, rel=1e-3)
    assert res["dollar_risk_usd"] == pytest.approx(40.0, rel=1e-3)

    # Now simulate an aggressive Half-Kelly = 0.50 -> Raw size = $5,000
    # $5,000 * 0.04 (4% stop) = $200 risk, which exceeds $150 cap!
    res_cap = KellySizingEngine.compute_composite_size(
        portfolio_equity=10000.0,
        win_rate=0.75,
        win_loss_ratio=3.0,
        entry_price=60000.0,
        stop_loss_price=57600.0,      # 4% stop
        take_profit_price=67200.0,
        kelly_fraction=0.75,
        max_dollar_risk_pct=0.015,    # $150 cap
    )
    assert res_cap["approved"] is True
    # Position size must be clamped so risk == $150 exactly: $150 / 0.04 = $3,750
    assert res_cap["position_size_usd"] == pytest.approx(3750.0, rel=1e-3)
    assert res_cap["dollar_risk_usd"] == pytest.approx(150.0, rel=1e-3)


def test_composite_size_rejection_on_excessive_fee_drag():
    # Target profit is only 0.15%, but fee is 0.10% -> Profit/Fee = 1.5x (< 3.0x min)
    res = KellySizingEngine.compute_composite_size(
        portfolio_equity=10000.0,
        win_rate=0.60,
        win_loss_ratio=2.0,
        entry_price=60000.0,
        stop_loss_price=59400.0,
        take_profit_price=60090.0,    # 0.15% profit target
        min_fee_drag_ratio=3.0,
    )
    assert res["approved"] is False
    assert "EXCESSIVE_FEE_DRAG" in res["rejection_reason"]


def test_composite_size_rejection_below_min_order():
    # Sizing for tiny portfolio $50 -> size ~$10 (< $15 min order)
    res = KellySizingEngine.compute_composite_size(
        portfolio_equity=50.0,
        win_rate=0.60,
        win_loss_ratio=2.0,
        entry_price=60000.0,
        stop_loss_price=58800.0,
        take_profit_price=63600.0,
        min_order_usd=15.0,
    )
    assert res["approved"] is False
    assert "POSITION_SIZE_BELOW_MIN_NOTIONAL" in res["rejection_reason"]
