# 🚀 StrategyOne: Autonomous Multi-Agent Trading System

StrategyOne is a production-grade, self-evolving automated quantitative crypto trading system designed for Binance (BTC/USDT). Built on a robust 9-agent autonomous committee architecture coordinated by a Master System Orchestrator, inspired by genetic algorithm strategy evolution and strict quantitative risk management.

---

## 🏗️ Architecture Overview

```
                                ┌───────────────────────────┐
                                │     🎛️ Orchestrator        │
                                └─────────────┬─────────────┘
                                              │
              ┌───────────────────────────────┴──────────────────────────────┐
              ▼                                                              ▼
   ┌───────────────────────┐                                      ┌───────────────────────┐
   │ 🗄️ Data Quality Agent │ (Sprint 1 - Absolute Veto)           │ 🛡️ Risk Agent         │
   └──────────┬────────────┘                                      └───────────────────────┘
              ▼
   ┌───────────────────────┐
   │ 📊 Technical Agent    │ (Sprint 2 - Multi-TF Confluence)
   └──────────┬────────────┘
              ▼
   ┌───────────────────────┐
   │ 🌍 Market Agent       │ (Sprint 3 - Derivatives & Crowding)
   └──────────┬────────────┘
              ▼
   ┌───────────────────────┐
   │ 🔮 Volatility Agent   │ (Sprint 4 - GARCH & Regime)
   └──────────┬────────────┘
              ▼
   ┌───────────────────────┐
   │ 🧬 Strategy Evolver   │ (Sprint 5-6)
   └──────────┬────────────┘
              ▼
   ┌───────────────────────┐
   │ 💵 Money Agent        │ (Sprint 8 - Kelly & Sizing)
   └──────────┬────────────┘
              ▼
   ┌───────────────────────┐
   │ ⚖️ Trade Decider      │ (Sprint 8 - 3-Layer Gatekeeper)
   └──────────┬────────────┘
              ▼
   ┌───────────────────────┐
   │ ⚡ Trade Executor     │ (Sprint 9 - Execution & Brackets)
   └───────────────────────┘
```

---

## 📦 Sprints Completed

### ✅ Sprint 1: Data Foundation & Data Quality Agent
1. **Config System (`config/settings.py`)**: Pydantic BaseSettings with type safety, multi-timeframe candle lookbacks (15m: 2688, 1h: 2160, 4h: 2160, 1d: 730), and quality thresholds.
2. **Event Bus (`core/events.py`)**: Decoupled asynchronous pub/sub messaging with circular audit history.
3. **Core Types (`core/types.py`)**: Standardized data contracts (`OHLCV`, `DataPacket`, `DataQualityReport`, `TechnicalAnalysisReport`, `MarketIntelligenceReport`, `AgentState`, `MarketBias`).
4. **Exchange Fetcher (`data/fetcher.py`)**: CCXT Binance fetcher with backward pagination, retry backoff, API weight tracking, and real-time bid-ask spread measurement.
5. **Data Cleaner & Validator (`data/cleaner.py`)**: Conservative forward-fill gap filling, flash crash / wick / volume anomaly detection, dynamic volatility surge checks, and quality scoring.
6. **Feature Engineering (`data/features.py`)**: Log returns, rolling volatility (24h and 7d), range %, body-to-wick ratio, and volume SMA ratio.
7. **Cache Manager (`data/cache_manager.py`)**: Local CSV caching with atomic swap writes and metadata inspection.
8. **Data Quality Agent (`agents/data_quality_agent.py`)**: Autonomous guardian with state machine (`HEALTHY`, `DEGRADED`, `HALTED`), cross-timeframe consistency audit, and **absolute veto power** (`is_tradeable = False` when score < 0.85).

### ✅ Sprint 2: Technical Analysis Agent & Confluence Engine
1. **Trend Indicators (`indicators/trend.py`)**: EMA Ribbon (20, 50, 200), EMA 50 Slope velocity, and SuperTrend(10, 3.0).
2. **Momentum Indicators (`indicators/momentum.py`)**: Wilder's RSI(14), MACD (12, 26, 9) signal & histogram, and MACD histogram acceleration.
3. **Volatility & Envelope (`indicators/volatility.py`)**: Bollinger Bands (%B and Bandwidth), Wilder's ATR(14), and Normalized ATR (NATR).
4. **Volume & Value (`indicators/volume.py`)**: Cumulative VWAP, rolling VWMA(20), and institutional volume divergence (VWMA vs SMA).
5. **Orthogonal Signal Normalizer (`indicators/normalizer.py`)**: Maps all 4 orthogonal dimensions into continuous bounded $[-1.0, +1.0]$ signals with exhaustion curve penalties.
6. **Multi-Timeframe Confluence Engine (`agents/confluence_engine.py`)**: Weighted synthesis ($15m: 15\%, 1h: 35\%, 4h: 35\%, 1d: 15\%$) with counter-trend trap dampening.
7. **Structural Key Levels (`indicators/levels.py`)**: Computes swing highs/lows, support/resistance zones, exact invalidation price ($P_{inv}$), and 1.5R/2.5R profit targets.
8. **Technical Analysis Agent (`agents/technical_agent.py`)**: Consumes clean `DataPacket`, strictly respects Data Quality veto power, and publishes `technical.analysis.report`.

### ✅ Sprint 3: Market Intelligence Agent (Derivatives & Positioning)
1. **Derivatives Fetcher (`data/derivatives_fetcher.py`)**: Binance Futures public endpoint client for 8h funding rates, 30-day funding rate history, Open Interest (OI), hourly OI history, and Top Trader Long/Short ratio.
2. **Macro Sentiment Fetcher (`data/sentiment_fetcher.py`)**: Alternative.me Fear & Greed Index client with 1-hour in-memory TTL caching and resilient neutral fallback.
3. **Positioning & Crowding Analyzer (`agents/positioning_analyzer.py`)**:
   - 30-day rolling Funding Rate Z-Score ($Z_{funding} = (F_t - \mu) / \sigma$).
   - 4h and 24h Open Interest velocity ($\Delta \text{OI}$).
   - Classical 4-Quadrant Positioning Matrix: Long Accumulation, Short Covering, Short Accumulation, Long Liquidation.
   - Crowding Penalty Factor ($P_{crowd} \in [0.0, 0.50]$) and Squeeze Warning generator.
4. **Market Intelligence Agent (`agents/market_agent.py`)**: Coordinates futures derivatives and sentiment data, evaluates positioning, publishes `market.intelligence.report`, and emits `market.intelligence.alert` on extreme squeeze crowding.

### ✅ Sprint 4: Volatility & Regime Forecaster Agent
1. **Volatility Estimator Suite (`models/volatility_models.py`)**:
   - High-Low Parkinson volatility ($5\times$ efficiency over standard deviation).
   - OHLC Garman-Klass volatility ($7.4\times$ statistical efficiency).
   - RiskMetrics EWMA ($\lambda=0.94$) volatility decay model.
   - Analytical GARCH(1,1) forward conditional variance projection.
2. **Statistical Regime Classifier (`models/regime_classifier.py`)**:
   - Rolling 30-day Parkinson volatility percentile ranking (`scipy.stats.percentileofscore`).
   - Bollinger Bandwidth compression squeeze detection ($\le 0.035$).
   - 3-state regime classification: `LOW_VOL_COMPRESSION`, `TRENDING_EXPANSION`, and `HIGH_VOL_CHAOS`.
3. **Dynamic Capital & Stop Multipliers (`models/volatility_multiplier.py`)**:
   - Dynamic capital multiplier ($0.40\times$ to $1.25\times$) downscaling size in high-volatility chaos.
   - Dynamic ATR stop distance multiplier ($1.2\times$ to $2.5\times \text{ATR}$) maintaining constant portfolio dollar risk.
4. **Volatility Forecaster Agent (`agents/volatility_agent.py`)**: Publishes `volatility.forecast.report` and emits `volatility.regime.change` events.

### ✅ Sprint 5: Strategy Evolution Foundation
1. **Strategy DNA Genome (`engine/genome.py`)**: 8 core genes (alleles) with boundary clamping, positive Risk/Reward invariants ($TP \ge 1.2 \times SL$), stochastic mutation, and arithmetic blend crossover.
2. **4 Core Crypto Species (`engine/species_strategies.py`)**: `MOMENTUM_TREND`, `MEAN_REVERSION`, `BREAKOUT_VOLATILITY`, and `REGIME_ADAPTIVE`.
3. **Ultra-Fast Vectorized Backtester (`engine/vectorized_backtester.py`)**:
   - Strict zero look-ahead bias ($P_t = S_{t-1}$).
   - Binance taker fee ($0.04\%$) + slippage ($0.01\%$) deduction on every position transition.
   - Full quantitative suite: Annualized Sharpe, Sortino (downside semi-variance), Calmar, Profit Factor, Win Rate, and Max Drawdown.
   - Sub-12ms execution speed per strategy.
4. **Population Manager (`engine/population_manager.py`)**: Manages 96 strategies (24 per species), seeds battle-tested heuristic archetypes, and ranks candidates.

### ✅ Sprint 6: Strategy Evolution Genetic Algorithm & Walk-Forward Suite
1. **Multi-Generation GA Engine (`engine/ga_engine.py`)**: Tournament selection ($k=3$), elitism (8 preserved), crossover, mutation, random immigrant injection (8 new), and dynamic regime-conditioned species quotas.
2. **Purged Walk-Forward Validator (`models/walk_forward.py`)**: 70/30 IS/OOS chronological split with 24-candle purging embargo and Deflated Sharpe Ratio (DSR) to eliminate multiple-testing selection bias.
3. **Monte Carlo Permutation Engine (`models/monte_carlo.py`)**: 1,000-run bootstrap reshuffling of trade returns calculating 95th-percentile worst-case drawdown and risk of ruin.
4. **Strategy Evolution Agent (`agents/strategy_evolution_agent.py`)**: Full Agent #5 executing multi-generational training, walk-forward validation, and generating real-time `TradeProposal` dataclasses with precision entry, ATR stops, and multi-tier 1.5R/2.5R profit targets.

### ✅ Sprint 7: Risk Management Agent & Portfolio Governance
1. **Fat-Tailed VaR & Expected Shortfall (`models/var_calculator.py`)**: Parametric, Non-Parametric Historical, and Cornish-Fisher leptokurtic Value at Risk with domain-of-monotonicity safeguards and sub-additive Expected Shortfall (CVaR).
2. **Portfolio & Drawdown Tracker (`models/portfolio_tracker.py`)**: Mark-to-market equity, High Water Mark, peak-to-trough drawdown %, multi-horizon calendar loss baselines (Daily UTC midnight, Weekly Monday UTC), consecutive loss counter, 2-hour cooldown timer, and atomic disk persistence (`data/portfolio_state.json`).
3. **Risk Management Agent (`agents/risk_agent.py`)**: Full Agent #6 operating a 5-tier state machine (GREEN, YELLOW, ORANGE, RED, CRITICAL, RECOVERY) with anti-chattering hysteresis deadbands, dynamic gross exposure ceilings conditioned on volatility regimes & crowd sentiment, and 7-gate proposal auditing with absolute veto power.

### ✅ Sprint 8: Money Management & Trade Decider Agents (Agents #7 & #8)
1. **Kelly Sizing & Volatility Parity (`models/kelly_sizing.py`)**: Full Kelly, Half-Kelly ($0.50 \cdot f^*$), inverse-ATR sizing, dollar risk cap ($R \le 1.5\%$ of equity), and transaction fee efficiency hurdle ($\ge 3\times$).
2. **Multi-Agent Consensus Matrix (`models/consensus_matrix.py`)**: Weighted voting matrix across all 7 domain agents with dynamic sentiment reweighting, conflict detection, and absolute veto propagation.
3. **Money Management Agent (`agents/money_agent.py`)**: Full Agent #7 enforcing 40% liquid reserve preservation, deployable capital budgeting, and producing `MoneyDecision`.
4. **Trade Decider Agent (`agents/decider_agent.py`)**: Full Agent #8 acting as the executive judge, enforcing the 3-Layer Defense Gatekeeper, and dispatching actionable `OrderIntent` dataclasses for execution.

### ✅ Sprint 9: Trade Execution Agent & Execution Engine (Agent #9)
1. **Precision Formatting & Exchange Gateway (`engine/exchange_client.py`)**: CCXT Binance client with automated tick size rounding, lot step size flooring, rate limit throttling, and $10.00 minimum notional enforcement.
2. **High-Fidelity Paper Trading Exchange (`engine/paper_exchange.py`)**: Zero-capital local execution simulation with realistic book spread crossing, post-only maker liquidity validation, stochastic slippage modeling ($0-3$ bps), and maker ($0.02\%$) / taker ($0.04\%$) fee deduction.
3. **Multi-Tier Bracket & OCO Manager (`engine/bracket_manager.py`)**: Automated bracket lifecycle managing Parent Entry $\rightarrow$ 100% Hard Stop Loss + 50% 1.5R Take Profit 1 + 50% 2.5R Runner Take Profit 2, with mutual OCO cancellation, breakeven ratcheting on TP1, and pre-fill invalidation cancellation.
4. **Trade Execution Agent (`agents/executor_agent.py`)**: Full Agent #9 coordinating execution routing (`PASSIVE_MAKER` vs `TAKER_AGGRESSIVE`), emergency circuit breaker flattening (`EVENT_EMERGENCY_FLATTEN`), and real-time reconciliation with `PortfolioTracker`.

### ✅ Sprint 10: Master Orchestrator, Live Scheduler Loop & State Resumption
1. **Multi-Horizon Timing Scheduler (`core/scheduler.py`)**: Wall-clock candle boundary alignment ($15\text{m}, 1\text{h}, 4\text{h}, 1\text{d}$) with microsecond drift compensation, high-frequency tick interval calculation, and periodic GA retrain cycle timers.
2. **Atomic State Checkpointing & Resumption (`models/system_state.py`)**: Safe atomic disk serialization (`.tmp` swap write) persisting orchestrator state, cycle metrics, risk tiers, active brackets, and open inventory for immediate crash recovery without state loss.
3. **Master System Orchestrator (`core/orchestrator.py`)**: Master container uniting all 9 autonomous agents, executing discrete decision cycles, handling tick-by-tick bracket monitoring, enforcing fail-closed data quality veto short-circuiting, and providing graceful shutdown handlers.

### ✅ Sprint 11: Real-Time Streamlit Monitoring Dashboard, Visual Boardroom & WebSocket Live Streaming
1. **High-Frequency WebSocket Live Streaming Gateway (`data/websocket_client.py`)**: Real-time Binance combined WebSocket client streaming sub-second `<symbol>@bookTicker` and `<symbol>@kline_15m` candle events with exponential backoff reconnect and direct feeding into `BracketOrderManager`.
2. **Interactive Streamlit Command Dashboard (`dashboard/app.py` & `dashboard/views/`)**: 5-panel visual cockpit featuring 9-agent Committee Boardroom, Active Brackets & Position Ladder, Risk & Portfolio Governance gauges, Backtest & Strategy Analytics, and Manual Operator Cockpit (Emergency Flatten, Circuit Breaker, GA retrain).
3. **Unified CLI Production Daemon Runtime (`main.py`)**: Command-line entry point supporting `--mode paper|testnet|live`, `--symbol`, `--dashboard`, `--no-ws`, and `--single-cycle` execution.

### ✅ Sprint 12: End-to-End Multi-Agent Historical Backtesting Simulator & Performance Tear-Sheet
1. **Institutional Performance Tear-Sheet (`models/tear_sheet.py`)**: Quantitative analytics suite computing Annualized Sharpe Ratio, Sortino Ratio, Calmar Ratio, Peak-to-Trough Max Drawdown & Duration, Profit Factor, Win Rate, Payoff Ratio, and serialized equity/underwater drawdown curves.
2. **Chronological Committee Backtester (`engine/committee_backtester.py`)**: Full 9-agent historical simulation walking forward through multi-timeframe candles with strict zero look-ahead bias, periodic GA model retraining, 7-gate risk audit, Half-Kelly sizing, and realistic multi-tier bracket execution.
3. **Interactive Backtest Analytics Dashboard (`dashboard/views/backtest.py`)**: Dedicated tab added to the Streamlit Cockpit allowing users to configure lookback windows, run backtests, and inspect interactive equity charts, underwater drawdowns, and performance KPIs.

---

## 🖥️ Running StrategyOne

### Launch Live Trading Daemon:
```bash
# Paper trading daemon with live WebSocket ticks
python main.py --mode paper --symbol BTC/USDT

# Paper trading daemon + Streamlit Cockpit Dashboard
python main.py --mode paper --symbol BTC/USDT --dashboard
```

### Launch Streamlit Dashboard Standalone:
```bash
streamlit run dashboard/app.py
```

---

## 🧪 Testing & Verification

Run the full automated test suite (163 tests):
```bash
pytest tests/ -v
```

Run end-to-end multi-agent verification scripts:
```bash
python scripts/verify_sprint1.py
python scripts/verify_sprint2.py
python scripts/verify_sprint3.py
python scripts/verify_sprint4.py
python scripts/verify_sprint5.py
python scripts/verify_sprint6.py
python scripts/verify_sprint7.py
python scripts/verify_sprint8.py
python scripts/verify_sprint9.py
python scripts/verify_sprint10.py
python scripts/verify_sprint11.py
python scripts/verify_sprint12.py
```


