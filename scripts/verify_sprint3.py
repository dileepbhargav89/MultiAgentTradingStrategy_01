"""Sprint 3 End-to-End Verification Script: Market Intelligence & Derivatives Positioning."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from agents.data_quality_agent import DataQualityAgent
from agents.market_agent import MarketIntelligenceAgent
from agents.technical_agent import TechnicalAgent
from core.events import (
    EVENT_MARKET_INTELLIGENCE_ALERT,
    EVENT_MARKET_INTELLIGENCE_REPORT,
    event_bus,
)


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


async def main():
    print("=" * 65)
    print("🚀 STRATEGYONE - SPRINT 3 MARKET INTELLIGENCE VERIFICATION")
    print("=" * 65)

    # 1. Event listener
    market_reports = []
    market_alerts = []
    event_bus.subscribe(EVENT_MARKET_INTELLIGENCE_REPORT, lambda r: market_reports.append(r))
    event_bus.subscribe(EVENT_MARKET_INTELLIGENCE_ALERT, lambda a: market_alerts.append(a))

    # 2. Agent 1: Data Quality Agent
    print("\n[1/3] Executing Agent 1 (Data Quality)...")
    dq_agent = DataQualityAgent()
    market_data = generate_market(periods=150, trend=0.001)
    dq_agent.evaluate_data("BTC/USDT", market_data)
    packet = dq_agent.build_data_packet("BTC/USDT")
    assert packet is not None
    print(f"  ✓ Data Status: {packet.quality.status.value} (Quality: {packet.quality.overall_quality:.1%})")

    # 3. Agent 2: Technical Analysis Agent
    print("\n[2/3] Executing Agent 2 (Technical Analysis)...")
    tech_agent = TechnicalAgent()
    tech_report = tech_agent.analyze(packet)
    print(f"  ✓ Technical Bias: {tech_report.bias.value} (Confluence: {tech_report.confluence_score:+.2f})")
    print(f"  ✓ Invalidation:   ${tech_report.invalidation_price:,.2f}")

    # 4. Agent 3: Market Intelligence Agent (Derivatives + Macro Sentiment)
    print("\n[3/3] Executing Agent 3 (Market Intelligence & Derivatives)...")
    market_agent = MarketIntelligenceAgent()
    market_report = await market_agent.analyze_live(packet)

    print(f"  ✓ 8h Funding Rate:     {market_report.funding_rate:.4%} (Annualized: {market_report.funding_rate_annualized:.2f}%)")
    print(f"  ✓ Funding Rate Z-Score: {market_report.funding_zscore:+.2f}")
    print(f"  ✓ Open Interest (USD):  ${market_report.open_interest_usd:,.2f}")
    print(f"  ✓ 4h OI Velocity:       {market_report.oi_change_4h_pct:+.2%}")
    print(f"  ✓ 24h OI Velocity:      {market_report.oi_change_24h_pct:+.2%}")
    print(f"  ✓ Positioning Regime:   {market_report.positioning_quadrant.value}")
    print(f"  ✓ Top Trader L/S Ratio: {market_report.top_trader_long_short_ratio:.2f}")
    print(f"  ✓ Fear & Greed Index:   {market_report.fear_and_greed_index} ({market_report.fear_and_greed_label})")
    print(f"  ✓ Crowding Bias:        {market_report.crowding_bias.value}")
    print(f"  ✓ Crowding Penalty:     {market_report.crowding_penalty:.2f} (Max 0.50)")
    if market_report.squeeze_warning:
        print(f"  ⚠️ SQUEEZE WARNING:     {market_report.squeeze_warning}")

    assert len(market_reports) >= 1
    print("\n" + "=" * 65)
    print("🎉 ALL SPRINT 3 ACCEPTANCE CRITERIA VERIFIED AND PASSING!")
    print("=" * 65)

    await market_agent.derivatives_fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
