import React, { useState } from 'react';
import { 
  ShieldCheck, Activity, Cpu, TrendingUp, RefreshCw, 
  Maximize2, Radio, AlertTriangle, Crosshair, CheckCircle2, ChevronRight, Info
} from 'lucide-react';

const AGENTS = [
  {
    id: 'data_quality',
    name: 'Data Quality Agent',
    role: 'Feed Integrity & Anomaly Veto',
    layer: 'GATEWAY',
    icon: ShieldCheck,
    signal: 'PASS',
    confidence: 0.99,
    status: 'HEALTHY',
    weight: 1.0,
    veto: false,
    latency: '1.2ms',
    color: '#10B981',
    description: 'Validates multi-timeframe candle stream against gaps, stale wall-clock timestamps, and zero-volume anomalies with zero lookahead bias.',
    metrics: [
      { label: 'Staleness', value: '3.8s' },
      { label: 'Feed Health', value: '100%' },
      { label: 'Missing Bars', value: '0' },
      { label: 'Imputation', value: 'Inactive' }
    ]
  },
  {
    id: 'market',
    name: 'Market Data Agent',
    role: 'Multi-Timeframe Technical Engine',
    layer: 'CONTEXT',
    icon: Activity,
    signal: 'BULLISH',
    confidence: 0.84,
    status: 'ACTIVE',
    weight: 1.0,
    veto: false,
    latency: '3.6ms',
    color: '#3B82F6',
    description: 'Computes synchronous indicators across 15m, 1h, 4h, and 1d feeds: RSI(14), ATR, Bollinger Bands, and MACD ribbons.',
    metrics: [
      { label: 'RSI (14)', value: '58.4' },
      { label: 'ATR (15m)', value: '$745.20' },
      { label: 'EMA Ribbon', value: 'Bullish Cross' },
      { label: 'MACD Hist', value: '+14.2' }
    ]
  },
  {
    id: 'regime',
    name: 'Regime Detection Agent',
    role: 'Market State Classification',
    layer: 'CONTEXT',
    icon: Cpu,
    signal: 'BULL_TREND',
    confidence: 0.88,
    status: 'ACTIVE',
    weight: 1.0,
    veto: false,
    latency: '4.1ms',
    color: '#F59E0B',
    description: 'Classifies continuous market structure into 4 quantitative regimes using ADX, ATR quantiles, and GARCH volatility estimation.',
    metrics: [
      { label: 'ADX Trend', value: '34.2 (Strong)' },
      { label: 'Hurst Exponent', value: '0.62 (Trending)' },
      { label: 'GARCH Vol', value: '48.5% Ann.' },
      { label: 'Regime Stability', value: '94.2%' }
    ]
  },
  {
    id: 'trend_following',
    name: 'Trend Following Agent',
    role: 'Macro Momentum & Breakaways',
    layer: 'ALPHA',
    icon: TrendingUp,
    signal: 'BUY',
    confidence: 0.85,
    status: 'ACTIVE',
    weight: 0.38,
    veto: false,
    latency: '2.0ms',
    color: '#10B981',
    description: 'Captures sustained directional momentum using dual EMA ribbons, Donchian Channel upper breakouts, and Supertrend confirmation.',
    metrics: [
      { label: 'Supertrend', value: 'BULLISH' },
      { label: 'Donchian Break', value: 'Active' },
      { label: 'EMA Alignment', value: '20 > 50 > 200' },
      { label: 'Signal Score', value: '+0.85' }
    ]
  },
  {
    id: 'mean_reversion',
    name: 'Mean Reversion Agent',
    role: 'Statistical Extremes Arbitrage',
    layer: 'ALPHA',
    icon: RefreshCw,
    signal: 'NEUTRAL',
    confidence: 0.45,
    status: 'STANDBY',
    weight: 0.28,
    veto: false,
    latency: '1.8ms',
    color: '#8B5CF6',
    description: 'Executes counter-trend fade entries during low-volatility rangebound regimes when Bollinger %B and RSI reach extreme deciles.',
    metrics: [
      { label: 'Bollinger %B', value: '0.68' },
      { label: 'Z-Score', value: '+0.82' },
      { label: 'RSI Divergence', value: 'None' },
      { label: 'Regime Fit', value: 'Inactive in Bull' }
    ]
  },
  {
    id: 'breakout',
    name: 'Breakout Agent',
    role: 'Volatility Expansion Hunter',
    layer: 'ALPHA',
    icon: Maximize2,
    signal: 'BUY',
    confidence: 0.78,
    status: 'ACTIVE',
    weight: 0.24,
    veto: false,
    latency: '2.4ms',
    color: '#06B6D4',
    description: 'Detects volatility compressions (Keltner-Bollinger squeeze) and enters on sudden volume-backed multi-bar price expansion.',
    metrics: [
      { label: 'Squeeze State', value: 'EXPANDING' },
      { label: 'Volume Surge', value: '1.84x SMA' },
      { label: 'Keltner Width', value: 'High' },
      { label: 'Signal Score', value: '+0.78' }
    ]
  },
  {
    id: 'sentiment',
    name: 'Sentiment Agent',
    role: 'Funding & Microstructure Radar',
    layer: 'ALPHA',
    icon: Radio,
    signal: 'BUY',
    confidence: 0.72,
    status: 'ACTIVE',
    weight: 0.10,
    veto: false,
    latency: '5.2ms',
    color: '#EC4899',
    description: 'Analyzes perpetual swap funding rates, open interest drift, and long/short positioning to protect against crowded market positioning.',
    metrics: [
      { label: 'Funding Rate', value: '+0.0102% (Neutral)' },
      { label: 'L/S Ratio', value: '1.14' },
      { label: 'Fear & Greed', value: '64 (Greed)' },
      { label: 'Crowded Bias', value: 'Normal' }
    ]
  },
  {
    id: 'risk',
    name: 'Risk Management Agent',
    role: 'Institutional Capital & VaR Governance',
    layer: 'GOVERNANCE',
    icon: AlertTriangle,
    signal: 'APPROVED',
    confidence: 0.96,
    status: 'ACTIVE',
    weight: 1.0,
    veto: false,
    latency: '3.1ms',
    color: '#EF4444',
    description: 'Enforces hard risk limits: Cornish-Fisher VaR 95%, CVaR expected shortfall, max 1.5% capital at risk per trade, and Kelly criterion sizing.',
    metrics: [
      { label: 'CF-VaR (95%)', value: '1.85% ($185.00)' },
      { label: 'CVaR (95%)', value: '2.65% ($265.00)' },
      { label: 'Position Sizing', value: '0.052 BTC' },
      { label: 'Drawdown Circuit', value: 'Normal (0.0% DD)' }
    ]
  },
  {
    id: 'execution',
    name: 'Execution Agent',
    role: 'Smart Order & OCO Bracket Engine',
    layer: 'EXECUTION',
    icon: Crosshair,
    signal: 'OCO_ACTIVE',
    confidence: 0.99,
    status: 'ARMED',
    weight: 1.0,
    veto: false,
    latency: '1.1ms',
    color: '#10B981',
    description: 'Manages multi-tier OCO order brackets: Take Profit 1 (50% scale), Take Profit 2 (runner), Trailing ATR Stop, and slippage monitoring.',
    metrics: [
      { label: 'Active Orders', value: '1 Entry / 3 Bracket' },
      { label: 'Stop Loss', value: '$62,500.00 (-1.0R)' },
      { label: 'TP1 Level', value: '$65,200.00 (+1.8R)' },
      { label: 'Trailing Stop', value: '$64,100.00 (Active)' }
    ]
  }
];

export default function AgentNetwork() {
  const [selectedAgent, setSelectedAgent] = useState(AGENTS[0]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top Banner explaining the interconnected flow */}
      <div className="glass-panel" style={{ padding: '18px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
            <span className="live-indicator"></span>
            <h2 style={{ fontSize: '18px', fontWeight: '700', letterSpacing: '-0.02em' }}>
              Autonomous 9-Agent Committee Consensus Network
            </h2>
            <span className="badge badge-green">Zero-Lookahead Synchronized</span>
          </div>
          <p style={{ color: 'var(--text-sub)', fontSize: '13px' }}>
            Multi-tier pipeline: Gateway Feed Validation → Macro Context & Regime → Alpha Species Committee → Genetic Weighting → Risk VaR Veto → Smart Execution
          </p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <div style={{ textAlign: 'right', borderRight: '1px solid var(--border-color)', paddingRight: '16px' }}>
            <div style={{ fontSize: '11px', color: 'var(--text-dim)', textTransform: 'uppercase' }}>Consensus Score</div>
            <div style={{ fontSize: '20px', fontWeight: '800', color: 'var(--green)' }}>+0.82 (STRONG BUY)</div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '11px', color: 'var(--text-dim)', textTransform: 'uppercase' }}>Risk Governance</div>
            <div style={{ fontSize: '20px', fontWeight: '800', color: '#60A5FA' }}>PASSED (0 Vetoes)</div>
          </div>
        </div>
      </div>

      {/* Main Grid: Interactive Network Architecture Visualizer */}
      <div style={{ display: 'grid', gridTemplateColumns: '2.5fr 1fr', gap: '20px' }}>
        {/* Left: Interconnected Flow Chart */}
        <div className="glass-panel" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Layer 1: Feed Gateway & Ingestion */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <span className="badge badge-green">Layer 1: Gateway & Validation</span>
              <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>Pre-Flight Ingestion & Feed Staleness Veto</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              {AGENTS.slice(0, 2).map((agent) => (
                <AgentCard 
                  key={agent.id} 
                  agent={agent} 
                  isSelected={selectedAgent.id === agent.id}
                  onClick={() => setSelectedAgent(agent)} 
                />
              ))}
            </div>
          </div>

          {/* Flow Connector Arrow */}
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', margin: '-10px 0' }}>
            <div style={{ height: '20px', width: '2px', background: 'linear-gradient(to bottom, #10B981, #F59E0B)' }}></div>
          </div>

          {/* Layer 2: Market Context & Volatility Regimes */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <span className="badge badge-amber">Layer 2: Macro Context & Regime</span>
              <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>Conditions Alpha Weights via GARCH & ADX</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '16px' }}>
              <AgentCard 
                agent={AGENTS[2]} 
                isSelected={selectedAgent.id === AGENTS[2].id}
                onClick={() => setSelectedAgent(AGENTS[2])} 
              />
            </div>
          </div>

          {/* Flow Connector Arrow */}
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', margin: '-10px 0' }}>
            <div style={{ height: '20px', width: '2px', background: 'linear-gradient(to bottom, #F59E0B, #3B82F6)' }}></div>
          </div>

          {/* Layer 3: Alpha Species Committee */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <span className="badge badge-blue">Layer 3: Alpha Strategy Committee</span>
              <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>Specialized Signal Generators Weighted by Genetic Algorithm</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '12px' }}>
              {AGENTS.slice(3, 7).map((agent) => (
                <AgentCard 
                  key={agent.id} 
                  agent={agent} 
                  isSelected={selectedAgent.id === agent.id}
                  onClick={() => setSelectedAgent(agent)} 
                />
              ))}
            </div>
          </div>

          {/* Flow Connector Arrow */}
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', margin: '-10px 0' }}>
            <div style={{ height: '20px', width: '2px', background: 'linear-gradient(to bottom, #3B82F6, #EF4444)' }}></div>
          </div>

          {/* Layer 4: Risk Governance & Execution */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <span className="badge badge-red">Layer 4: Risk Governance & Execution</span>
              <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>Cornish-Fisher VaR Sizing & OCO Bracket Engine</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              {AGENTS.slice(7, 9).map((agent) => (
                <AgentCard 
                  key={agent.id} 
                  agent={agent} 
                  isSelected={selectedAgent.id === agent.id}
                  onClick={() => setSelectedAgent(agent)} 
                />
              ))}
            </div>
          </div>

        </div>

        {/* Right: Detailed Agent Telemetry & Metric Inspector */}
        <div className="glass-panel" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <selectedAgent.icon size={22} style={{ color: selectedAgent.color }} />
              <h3 style={{ fontSize: '16px', fontWeight: '700' }}>{selectedAgent.name}</h3>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-dim)', marginBottom: '12px' }}>{selectedAgent.role}</div>
            <p style={{ fontSize: '13px', color: 'var(--text-sub)', lineHeight: '1.5', background: 'rgba(0,0,0,0.2)', padding: '12px', borderRadius: '8px' }}>
              {selectedAgent.description}
            </p>
          </div>

          {/* Key State Badges */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>STATUS</div>
              <div style={{ fontSize: '14px', fontWeight: '700', color: selectedAgent.color }}>{selectedAgent.status}</div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>SIGNAL</div>
              <div style={{ fontSize: '14px', fontWeight: '700', color: 'var(--text-main)' }}>{selectedAgent.signal}</div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>CONFIDENCE</div>
              <div style={{ fontSize: '14px', fontWeight: '700', color: 'var(--green)' }}>{(selectedAgent.confidence * 100).toFixed(0)}%</div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>GA WEIGHT</div>
              <div style={{ fontSize: '14px', fontWeight: '700', color: 'var(--blue)' }}>{(selectedAgent.weight * 100).toFixed(0)}%</div>
            </div>
          </div>

          {/* Live Dynamic Telemetry Metrics */}
          <div>
            <div style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-dim)', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Real-Time Metrics & Indicators
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {selectedAgent.metrics.map((m, idx) => (
                <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.04)' }}>
                  <span style={{ fontSize: '12px', color: 'var(--text-sub)' }}>{m.label}</span>
                  <span className="font-mono" style={{ fontSize: '13px', fontWeight: '600', color: 'var(--text-main)' }}>{m.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Veto Protection Status */}
          <div style={{ padding: '12px', borderRadius: '8px', background: selectedAgent.veto ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.08)', border: `1px solid ${selectedAgent.veto ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.2)'}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {selectedAgent.veto ? <AlertTriangle size={16} color="#EF4444" /> : <CheckCircle2 size={16} color="#10B981" />}
              <span style={{ fontSize: '12px', fontWeight: '600', color: selectedAgent.veto ? '#F87171' : '#34D399' }}>
                {selectedAgent.veto ? 'Veto Intercept Active' : 'No Veto Triggered (Passed)'}
              </span>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
              {selectedAgent.veto ? selectedAgent.veto_reason : 'Autonomous risk threshold validated with zero violations.'}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

function AgentCard({ agent, isSelected, onClick }) {
  const Icon = agent.icon;
  return (
    <div 
      onClick={onClick}
      className="glass-card" 
      style={{ 
        padding: '14px 16px', 
        cursor: 'pointer',
        borderColor: isSelected ? agent.color : undefined,
        boxShadow: isSelected ? `0 0 16px ${agent.color}33` : undefined,
        position: 'relative',
        overflow: 'hidden'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ padding: '6px', borderRadius: '6px', background: `${agent.color}22` }}>
            <Icon size={16} style={{ color: agent.color }} />
          </div>
          <div>
            <div style={{ fontSize: '13px', fontWeight: '700', color: 'var(--text-main)' }}>{agent.name}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>{agent.latency}</div>
          </div>
        </div>
        <span className={`badge ${agent.signal === 'BUY' || agent.signal === 'PASS' || agent.signal === 'APPROVED' ? 'badge-green' : agent.signal === 'BULL_TREND' ? 'badge-amber' : 'badge-purple'}`} style={{ fontSize: '10px', padding: '2px 8px' }}>
          {agent.signal}
        </span>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '8px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Confidence:</span>
        <span className="font-mono" style={{ fontSize: '12px', fontWeight: '700', color: agent.color }}>
          {(agent.confidence * 100).toFixed(0)}%
        </span>
      </div>
    </div>
  );
}
