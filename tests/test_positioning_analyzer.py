"""Unit tests for PositioningAnalyzer calculations and regime mapping."""

import pandas as pd
import pytest
from agents.positioning_analyzer import PositioningAnalyzer
from core.types import CrowdingBias, PositioningQuadrant


def test_funding_zscore():
    analyzer = PositioningAnalyzer()
    # 30-day simulated funding rates with mean 0.0001 (0.01%) and std 0.00005
    history = pd.DataFrame({
        "funding_rate": [0.00005, 0.00010, 0.00015, 0.00010, 0.00010, 0.00008, 0.00012]
    })

    # High funding rate 0.0004 should have positive Z-score > 2.0
    z = analyzer.calculate_funding_zscore(0.00040, history)
    assert z > 2.0

    # Negative funding rate should have negative Z-score
    z_neg = analyzer.calculate_funding_zscore(-0.00020, history)
    assert z_neg < -2.0


def test_oi_velocity():
    analyzer = PositioningAnalyzer()
    # 48 hours of OI data
    oi_values = [50000.0 + i * 200.0 for i in range(48)]  # Steady climb
    oi_df = pd.DataFrame({"sum_open_interest": oi_values})

    chg_4h, chg_24h = analyzer.calculate_oi_velocity(oi_df)
    assert chg_4h > 0.0
    assert chg_24h > 0.0
    # Over 24 hours, from ~55200 to 59400 is ~7.6%
    assert chg_24h > 0.05


def test_positioning_quadrants():
    analyzer = PositioningAnalyzer()

    # Price UP + OI UP -> LONG_ACCUMULATION
    assert analyzer.classify_positioning_quadrant(0.03, 0.04) == PositioningQuadrant.LONG_ACCUMULATION

    # Price UP + OI DOWN -> SHORT_COVERING
    assert analyzer.classify_positioning_quadrant(0.03, -0.04) == PositioningQuadrant.SHORT_COVERING

    # Price DOWN + OI UP -> SHORT_ACCUMULATION
    assert analyzer.classify_positioning_quadrant(-0.03, 0.04) == PositioningQuadrant.SHORT_ACCUMULATION

    # Price DOWN + OI DOWN -> LONG_LIQUIDATION
    assert analyzer.classify_positioning_quadrant(-0.03, -0.04) == PositioningQuadrant.LONG_LIQUIDATION

    # Flat moves -> BALANCED
    assert analyzer.classify_positioning_quadrant(0.001, -0.001) == PositioningQuadrant.BALANCED


def test_crowding_and_penalty():
    analyzer = PositioningAnalyzer()

    # Extreme long crowding: Funding Z=3.0, OI climbing, Extreme Greed FGI=85
    bias, penalty, warn = analyzer.calculate_crowding_and_penalty(
        funding_zscore=3.0,
        oi_change_24h_pct=0.06,
        top_trader_ls=0.85,  # Divergence: top traders are short
        fgi_value=85,
    )

    assert bias == CrowdingBias.CROWDED_LONG
    assert penalty >= 0.30
    assert warn is not None

    # Extreme short crowding (Short Squeeze setup): Funding Z=-3.0, OI climbing, Extreme Fear FGI=15
    bias_sq, penalty_sq, warn_sq = analyzer.calculate_crowding_and_penalty(
        funding_zscore=-3.0,
        oi_change_24h_pct=0.06,
        top_trader_ls=1.20,
        fgi_value=15,
    )

    assert bias_sq == CrowdingBias.CROWDED_SHORT
    assert penalty_sq >= 0.30
    assert "SQUEEZE" in warn_sq


def test_compound_crowding_penalty():
    analyzer = PositioningAnalyzer()
    # 4 signals aligning: Funding Z=1.6, OI=5%, FGI=80, TopTrader LS=0.85
    _, penalty_compound, _ = analyzer.calculate_crowding_and_penalty(
        funding_zscore=1.6,
        oi_change_24h_pct=0.05,
        top_trader_ls=0.85,
        fgi_value=80,
    )
    simple_sum = (1.6 - 1.5) * 0.12 + 0.10 + 0.08 + 0.10
    assert penalty_compound > simple_sum


def test_squeeze_fires_at_2_0_zscore():
    analyzer = PositioningAnalyzer()
    # Z=2.0 and OI=0.025 (>2%) -> should trigger IMMINENT_LONG_SQUEEZE with tighter threshold
    _, _, warn = analyzer.calculate_crowding_and_penalty(
        funding_zscore=2.0,
        oi_change_24h_pct=0.025,
        top_trader_ls=1.0,
        fgi_value=50,
    )
    assert warn == "IMMINENT_LONG_SQUEEZE"

