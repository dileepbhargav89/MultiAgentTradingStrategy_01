"""Sprint 2 End-to-End Verification Script: Technical Analysis & Confluence Engine."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from agents.data_quality_agent import DataQualityAgent
from agents.technical_agent import TechnicalAgent
from core.events import EVENT_TECHNICAL_REPORT, event_bus
from core.types import MarketBias


def generate_market(periods: int = 120, trend: float = 0.001) -> dict[str, pd.DataFrame]:
    now = datetime.now(timezone.utc)
    tf_minutes = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    dataset = {}

    for tf, mins in tf_minutes.items():
        records = []
        base_time = now - timedelta(minutes=periods * mins)
        price = 64000.0
        for i in range(periods):
            ts = base_time + timedelta(minutes=i * mins)
            o = price
            c = price * (1.0 + trend)
            h = max(o, c) * 1.003
            l = min(o, c) * 0.997
            v = 600.0 + (i % 7) * 30.0
            records.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})
            price = c
        dataset[tf] = pd.DataFrame(records)

    return dataset


def main():
    print("=" * 65)
    print("🚀 STRATEGYONE - SPRINT 2 TECHNICAL AGENT VERIFICATION")
    print("=" * 65)

    # 1. Event listener
    received_reports = []
    event_bus.subscribe(EVENT_TECHNICAL_REPORT, lambda r: received_reports.append(r))

    # 2. Acquire Clean Market Data via Agent 1 (Data Quality Agent)
    print("\n[1/4] Processing multi-timeframe data via Agent 1 (Data Quality)...")
    dq_agent = DataQualityAgent()
    market_data = generate_market(periods=150, trend=0.0015)  # Healthy bull market
    dq_report = dq_agent.evaluate_data("BTC/USDT", market_data)
    assert dq_report.is_tradeable is True
    print(f"  ✓ Data Quality Score: {dq_report.overall_quality:.1%}")
    print(f"  ✓ Tradeable Status:   {dq_report.is_tradeable} (State: {dq_report.status.value})")

    packet = dq_agent.build_data_packet("BTC/USDT")
    assert packet is not None

    # 3. Execute Agent 2 (Technical Analysis Agent)
    print("\n[2/4] Executing Agent 2 (Technical Analysis & Confluence)...")
    tech_agent = TechnicalAgent()
    tech_report = tech_agent.analyze(packet)

    print(f"  ✓ Market Bias:        {tech_report.bias.value}")
    print(f"  ✓ Confluence Score:   {tech_report.confluence_score:+.2f} [-1.0 to +1.0]")
    print(f"  ✓ Current Price:      ${packet.latest_price:,.2f}")
    print(f"  ✓ 1H ATR (14):        ${tech_report.atr_14:,.2f}")
    print(f"  ✓ Invalidation Stop:  ${tech_report.invalidation_price:,.2f}")
    print(f"  ✓ Profit Target 1 (1.5R): ${tech_report.target_1r:,.2f}")
    print(f"  ✓ Profit Target 2 (2.5R): ${tech_report.target_2r:,.2f}")

    print("\n[3/4] Timeframe & Dimension Breakdowns:")
    for tf, score in tech_report.timeframe_scores.items():
        print(f"  • Timeframe {tf:>3}: {score:+.2f}")
    for dim, score in tech_report.dimension_scores.items():
        print(f"  • Dimension {dim.title():<10}: {score:+.2f}")

    # 4. Verify Defensive Veto Interaction
    print("\n[4/4] Verifying Data Quality Veto Integration with Technical Agent...")
    bad_data = generate_market(periods=150)
    # Corrupt data with invalid physical candles
    bad_data["1h"].loc[10:30, "high"] = 1.0
    bad_data["1h"].loc[10:30, "low"] = 99999.0

    dq_agent.evaluate_data("BTC/USDT", bad_data)
    bad_packet = dq_agent.build_data_packet("BTC/USDT")
    assert bad_packet.quality.is_tradeable is False

    vetoed_report = tech_agent.analyze(bad_packet)
    print(f"  ✓ Under Veto Bias:    {vetoed_report.bias.value}")
    print(f"  ✓ Under Veto Score:   {vetoed_report.confluence_score:+.2f}")
    assert vetoed_report.bias == MarketBias.NEUTRAL
    assert vetoed_report.confluence_score == 0.0

    print("\n" + "=" * 65)
    print("🎉 ALL SPRINT 2 CRITERIA VERIFIED AND PASSING SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    main()
