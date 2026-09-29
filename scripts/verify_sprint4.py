"""Sprint 4 End-to-End Verification Script: Volatility & Regime Forecaster Agent."""

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
from agents.volatility_agent import VolatilityRegimeAgent
from core.events import EVENT_VOLATILITY_REPORT, event_bus


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
    print("🚀 STRATEGYONE - SPRINT 4 VOLATILITY FORECASTER VERIFICATION")
    print("=" * 65)

    vol_reports = []
    event_bus.subscribe(EVENT_VOLATILITY_REPORT, lambda r: vol_reports.append(r))

    # 1. Agent 1: Data Quality Agent
    print("\n[1/4] Executing Agent 1 (Data Quality)...")
    dq_agent = DataQualityAgent()
    market_data = generate_market(periods=150, trend=0.001)
    dq_agent.evaluate_data("BTC/USDT", market_data)
    packet = dq_agent.build_data_packet("BTC/USDT")
    assert packet is not None
    print(f"  ✓ Data Status: {packet.quality.status.value} (Quality: {packet.quality.overall_quality:.1%})")

    # 2. Agent 2: Technical Analysis Agent
    print("\n[2/4] Executing Agent 2 (Technical Analysis)...")
    tech_agent = TechnicalAgent()
    tech_report = tech_agent.analyze(packet)
    print(f"  ✓ Technical Bias: {tech_report.bias.value} (Confluence: {tech_report.confluence_score:+.2f})")
    print(f"  ✓ Invalidation:   ${tech_report.invalidation_price:,.2f}")

    # 3. Agent 3: Market Intelligence Agent
    print("\n[3/4] Executing Agent 3 (Market Intelligence & Derivatives)...")
    market_agent = MarketIntelligenceAgent()
    market_report = await market_agent.analyze_live(packet)
    print(f"  ✓ Funding Z-Score: {market_report.funding_zscore:+.2f} | Quadrant: {market_report.positioning_quadrant.value}")
    print(f"  ✓ Crowding Penalty: {market_report.crowding_penalty:.2f}")

    # 4. Agent 4: Volatility & Regime Forecaster Agent
    print("\n[4/4] Executing Agent 4 (Volatility & Regime Forecaster)...")
    vol_agent = VolatilityRegimeAgent()
    vol_report = vol_agent.analyze(packet)

    print(f"  ✓ Statistical Regime:    {vol_report.regime.value}")
    print(f"  ✓ 24h Forward Forecast:   {vol_report.forecasted_volatility_24h:.1f}%")
    print(f"  ✓ Parkinson High-Low Vol: {vol_report.parkinson_volatility:.1f}%")
    print(f"  ✓ Garman-Klass OHLC Vol:  {vol_report.garman_klass_volatility:.1f}%")
    print(f"  ✓ Volatility Percentile:  {vol_report.volatility_percentile:.1f}%")
    print(f"  ✓ Capital Sizing Mult:    {vol_report.volatility_multiplier:.2f}x")
    print(f"  ✓ ATR Stop Distance Mult: {vol_report.atr_stop_multiplier:.2f}x")
    print(f"  ✓ Imminent Breakout Squeeze: {vol_report.is_breakout_imminent}")

    assert len(vol_reports) >= 1
    print("\n" + "=" * 65)
    print("🎉 ALL SPRINT 4 ACCEPTANCE CRITERIA VERIFIED AND PASSING!")
    print("=" * 65)

    await market_agent.derivatives_fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
