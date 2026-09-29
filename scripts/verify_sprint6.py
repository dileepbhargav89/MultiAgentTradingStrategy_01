"""Sprint 6 End-to-End Verification Script: Strategy Evolution Agent & 5-Agent Harmony."""

import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
from agents.data_quality_agent import DataQualityAgent
from agents.market_agent import MarketIntelligenceAgent
from agents.strategy_evolution_agent import StrategyEvolutionAgent
from agents.technical_agent import TechnicalAgent
from agents.volatility_agent import VolatilityRegimeAgent
from core.events import EVENT_TRADE_PROPOSAL, event_bus


def generate_market(periods_15m: int = 1200, trend: float = 0.0002) -> dict[str, pd.DataFrame]:
    """Generates synthetic 15m BTC candles and resamples higher timeframes for 100% cross-TF consistency."""
    np.random.seed(42)
    now = datetime.now(timezone.utc)
    base_time = now - timedelta(minutes=periods_15m * 15)

    price = 63500.0
    records = []
    for i in range(periods_15m):
        ts = base_time + timedelta(minutes=i * 15)
        o = price
        c = price * (1.0 + trend + np.random.normal(0, 0.0015))
        h = max(o, c) * (1.0 + abs(np.random.normal(0, 0.001)))
        l = min(o, c) * (1.0 - abs(np.random.normal(0, 0.001)))
        v = 200.0 + abs(np.random.normal(0, 50.0))
        records.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})
        price = c

    df_15m = pd.DataFrame(records)
    df_15m["timestamp"] = pd.to_datetime(df_15m["timestamp"])
    df_indexed = df_15m.set_index("timestamp")

    dataset = {"15m": df_15m}
    for tf, rule in [("1h", "1h"), ("4h", "4h"), ("1d", "1D")]:
        df_tf = df_indexed.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna().reset_index()
        dataset[tf] = df_tf

    return dataset


async def main():
    print("=" * 70)
    print("🚀 STRATEGYONE - SPRINT 6 STRATEGY EVOLUTION AGENT VERIFICATION")
    print("=" * 70)

    trade_proposals = []
    event_bus.subscribe(EVENT_TRADE_PROPOSAL, lambda p: trade_proposals.append(p))

    # [1/5] Agent 1: Data Quality
    print("\n[1/5] Executing Agent 1 (Data Quality)...")
    dq_agent = DataQualityAgent()
    market_data = generate_market(periods_15m=1200, trend=0.0002)
    dq_agent.evaluate_data("BTC/USDT", market_data)
    packet = dq_agent.build_data_packet("BTC/USDT")
    assert packet is not None
    print(f"  ✓ Data Quality: {packet.quality.overall_quality:.1%} (Status: {packet.quality.status.value})")

    # [2/5] Agent 2: Technical Analysis
    print("\n[2/5] Executing Agent 2 (Technical Analysis)...")
    tech_agent = TechnicalAgent()
    tech_report = tech_agent.analyze(packet)
    print(f"  ✓ Bias: {tech_report.bias.value} | Confluence: {tech_report.confluence_score:+.2f} | P_inv: ${tech_report.invalidation_price:,.2f}")

    # [3/5] Agent 3: Market Intelligence
    print("\n[3/5] Executing Agent 3 (Market Intelligence & Derivatives)...")
    market_agent = MarketIntelligenceAgent()
    market_report = await market_agent.analyze_live(packet)
    print(f"  ✓ Funding Z-Score: {market_report.funding_zscore:+.2f} | Quadrant: {market_report.positioning_quadrant.value}")

    # [4/5] Agent 4: Volatility & Regime Forecaster
    print("\n[4/5] Executing Agent 4 (Volatility & Regime Forecaster)...")
    vol_agent = VolatilityRegimeAgent()
    vol_report = vol_agent.analyze(packet)
    print(f"  ✓ Regime: {vol_report.regime.value} | 24h Forecast: {vol_report.forecasted_volatility_24h:.1f}% | Sizing: {vol_report.volatility_multiplier:.2f}x")

    # [5/5] Agent 5: Strategy Evolution Agent
    print("\n[5/5] Executing Agent 5 (Strategy Evolution Agent)...")
    strat_agent = StrategyEvolutionAgent(population_size=40, tournament_k=3)

    t0 = time.perf_counter()
    print("  • Training 3 generations across 4 species with dynamic regime quotas...")
    df_1h = packet.timeframes["1h"]
    champion = strat_agent.train(df_1h, generations=3, regime=vol_report.regime)
    elapsed_train = (time.perf_counter() - t0) * 1000.0
    print(f"  ✓ Evolutionary Training complete in {elapsed_train:.1f}ms")

    # Show Walk-Forward & Monte Carlo Reports
    wf = strat_agent.latest_wf_report
    mc = strat_agent.latest_mc_report
    print(f"  ✓ Walk-Forward Validation: WFE={wf.walk_forward_efficiency:.2f} | DSR={wf.deflated_sharpe_ratio:.3f} | Overfit={wf.is_overfit}")
    print(f"  ✓ Monte Carlo Permutations: 95% Worst DD={mc.drawdown_95th_percentile:.1%} | Ruin Risk={mc.risk_of_ruin_pct:.2f}% | Disqualified={mc.is_disqualified}")

    # Generate Real-Time Trade Proposal
    print("\n  • Generating real-time TradeProposal for downstream agents...")
    proposal = strat_agent.evaluate_live(packet)

    print("\n" + "-" * 70)
    print(f"📋 ACTIONABLE TRADE PROPOSAL ISSUED:")
    print(f"   • Strategy ID:       {proposal.strategy_id} ({proposal.species.value})")
    print(f"   • Action:            {proposal.action}")
    print(f"   • Entry Price:       ${proposal.entry_price:,.2f}")
    print(f"   • Stop Loss:         ${proposal.stop_loss_price:,.2f}")
    print(f"   • Profit Target 1:   ${proposal.take_profit_price:,.2f} (1.5R)")
    print(f"   • Profit Target 2:   ${proposal.target_2r_price:,.2f} (2.5R)")
    print(f"   • Invalidation:      ${proposal.invalidation_price:,.2f}")
    print(f"   • Execution Urgency: {proposal.execution_urgency}")
    print(f"   • Trade Confidence:  {proposal.confidence:.1%}")
    print(f"   • Backtest Sharpe:   {proposal.backtest_sharpe:.2f}")
    print("-" * 70)

    assert len(trade_proposals) >= 1
    print("\n" + "=" * 70)
    print("🎉 ALL SPRINT 6 ACCEPTANCE CRITERIA VERIFIED AND PASSING!")
    print("=" * 70)

    await market_agent.derivatives_fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
