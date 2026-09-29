import React from 'react';
import { 
  TrendingUp, Shield, Target, ArrowUpRight, CheckCircle2, Clock, 
  Layers, DollarSign, Crosshair, AlertCircle
} from 'lucide-react';

export default function PositionLadder() {
  const position = {
    symbol: 'BTC/USDT',
    side: 'LONG',
    entryPrice: 63450.0,
    currentPrice: 65120.0,
    sizeBtc: 0.052,
    notional: 3386.24,
    unrealizedPnl: 86.84,
    unrealizedPnlPct: 2.63,
    stopLoss: 62500.0,
    trailingStop: 64100.0,
    tp1: 65200.0,
    tp2: 66800.0,
    riskUsd: 49.40,
    currentR: 1.76,
    entryTime: '2026-09-26 14:15:00 UTC'
  };

  // Bracket orders
  const brackets = [
    { id: 'ORD-SL-01', type: 'STOP_LOSS_MARKET', trigger: '$62,500.00', amount: '0.052 BTC', status: 'ARMED', rLevel: '-1.0R', color: '#EF4444' },
    { id: 'ORD-TS-01', type: 'TRAILING_STOP', trigger: '$64,100.00', amount: '0.052 BTC', status: 'ACTIVE (LOCKED)', rLevel: '+0.68R', color: '#F59E0B' },
    { id: 'ORD-TP-01', type: 'TAKE_PROFIT_LIMIT (50%)', trigger: '$65,200.00', amount: '0.026 BTC', status: 'PENDING', rLevel: '+1.84R', color: '#10B981' },
    { id: 'ORD-TP-02', type: 'TAKE_PROFIT_LIMIT (Runner)', trigger: '$66,800.00', amount: '0.026 BTC', status: 'PENDING', rLevel: '+3.53R', color: '#3B82F6' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* Top Banner: Active Position Overview Card */}
      <div className="glass-panel" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span className="badge badge-green" style={{ fontSize: '13px' }}>LONG</span>
              <h2 style={{ fontSize: '22px', fontWeight: '800', letterSpacing: '-0.02em' }}>{position.symbol} Perpetual</h2>
              <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>Entry: {position.entryTime}</span>
            </div>
            <div style={{ display: 'flex', gap: '16px', marginTop: '6px' }}>
              <span style={{ fontSize: '13px', color: 'var(--text-sub)' }}>
                Position Size: <strong style={{ color: 'var(--text-main)' }}>{position.sizeBtc} BTC</strong> (${position.notional.toLocaleString()})
              </span>
              <span style={{ fontSize: '13px', color: 'var(--text-sub)' }}>
                Entry Fill: <strong className="font-mono" style={{ color: 'var(--text-main)' }}>${position.entryPrice.toLocaleString()}</strong>
              </span>
              <span style={{ fontSize: '13px', color: 'var(--text-sub)' }}>
                Mark Price: <strong className="font-mono" style={{ color: '#60A5FA' }}>${position.currentPrice.toLocaleString()}</strong>
              </span>
            </div>
          </div>

          {/* Unrealized PnL Block */}
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-dim)', textTransform: 'uppercase' }}>Unrealized Gain / PnL</div>
            <div className="font-mono" style={{ fontSize: '28px', fontWeight: '900', color: 'var(--green)' }}>
              +${position.unrealizedPnl.toFixed(2)}
            </div>
            <div style={{ fontSize: '14px', fontWeight: '700', color: '#34D399' }}>
              +{position.unrealizedPnlPct}% (+{position.currentR}R)
            </div>
          </div>
        </div>

        {/* Visual R-Multiple Ladder Bar */}
        <div style={{ background: 'rgba(0,0,0,0.3)', padding: '20px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
            <span style={{ fontSize: '13px', fontWeight: '700', color: 'var(--text-main)' }}>
              Active Position Risk & R-Multiple Ladder Progress
            </span>
            <span className="font-mono" style={{ fontSize: '12px', color: '#10B981', fontWeight: '700' }}>
              Current Trajectory: +{position.currentR}R of Initial Risk (${position.riskUsd})
            </span>
          </div>

          {/* Visual Progress Track */}
          <div style={{ position: 'relative', height: '14px', background: '#1E293B', borderRadius: '8px', overflow: 'hidden', margin: '24px 0 32px 0' }}>
            {/* Loss zone (0 to -1R) */}
            <div style={{ position: 'absolute', left: '0%', width: '25%', height: '100%', background: 'rgba(239, 68, 68, 0.4)' }}></div>
            {/* Profit zone (0 to 3.5R) */}
            <div style={{ position: 'absolute', left: '25%', width: '75%', height: '100%', background: 'rgba(16, 185, 129, 0.2)' }}></div>
            {/* Current Fill Progress */}
            <div style={{ position: 'absolute', left: '25%', width: '38%', height: '100%', background: 'linear-gradient(90deg, #10B981, #3B82F6)' }}></div>
          </div>

          {/* Pin Markers along the ladder */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '8px', textAlign: 'center' }}>
            {/* Stop Loss Pin */}
            <div style={{ borderLeft: '2px solid #EF4444', paddingLeft: '8px', textAlign: 'left' }}>
              <div style={{ fontSize: '11px', color: '#EF4444', fontWeight: '700' }}>STOP LOSS (-1.0R)</div>
              <div className="font-mono" style={{ fontSize: '13px', fontWeight: '700' }}>${position.stopLoss.toLocaleString()}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Max Loss: -${position.riskUsd}</div>
            </div>

            {/* Breakeven Pin */}
            <div style={{ borderLeft: '2px solid #94A3B8', paddingLeft: '8px', textAlign: 'left' }}>
              <div style={{ fontSize: '11px', color: '#94A3B8', fontWeight: '700' }}>BREAKEVEN (0.0R)</div>
              <div className="font-mono" style={{ fontSize: '13px', fontWeight: '700' }}>${position.entryPrice.toLocaleString()}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Initial Cost Basis</div>
            </div>

            {/* Trailing Stop Pin */}
            <div style={{ borderLeft: '2px solid #F59E0B', paddingLeft: '8px', textAlign: 'left' }}>
              <div style={{ fontSize: '11px', color: '#F59E0B', fontWeight: '700' }}>TRAILING STOP (+0.68R)</div>
              <div className="font-mono" style={{ fontSize: '13px', fontWeight: '700' }}>${position.trailingStop.toLocaleString()}</div>
              <div style={{ fontSize: '11px', color: '#FBBF24' }}>+$33.60 Locked In</div>
            </div>

            {/* Take Profit 1 Pin */}
            <div style={{ borderLeft: '2px solid #10B981', paddingLeft: '8px', textAlign: 'left' }}>
              <div style={{ fontSize: '11px', color: '#10B981', fontWeight: '700' }}>TAKE PROFIT 1 (+1.84R)</div>
              <div className="font-mono" style={{ fontSize: '13px', fontWeight: '700' }}>${position.tp1.toLocaleString()}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Scale Out 50% Size</div>
            </div>

            {/* Take Profit 2 Pin */}
            <div style={{ borderLeft: '2px solid #3B82F6', paddingLeft: '8px', textAlign: 'left' }}>
              <div style={{ fontSize: '11px', color: '#3B82F6', fontWeight: '700' }}>TARGET 2 (+3.53R)</div>
              <div className="font-mono" style={{ fontSize: '13px', fontWeight: '700' }}>${position.tp2.toLocaleString()}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Runner Target</div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Grid: OCO Bracket Tree & Live Fills */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.8fr 1.2fr', gap: '20px' }}>
        
        {/* OCO Bracket Tree Table */}
        <div className="glass-panel" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <Layers size={18} color="#3B82F6" />
            <h3 style={{ fontSize: '16px', fontWeight: '700' }}>Resting OCO Bracket Lifecycle Tree</h3>
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-dim)', fontSize: '11px', textTransform: 'uppercase' }}>
                <th style={{ padding: '8px 12px' }}>Order ID</th>
                <th style={{ padding: '8px 12px' }}>Order Type</th>
                <th style={{ padding: '8px 12px' }}>Trigger Level</th>
                <th style={{ padding: '8px 12px' }}>Amount</th>
                <th style={{ padding: '8px 12px' }}>R-Multiple</th>
                <th style={{ padding: '8px 12px' }}>Lifecycle Status</th>
              </tr>
            </thead>
            <tbody>
              {brackets.map((b) => (
                <tr key={b.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)', fontSize: '13px' }}>
                  <td className="font-mono" style={{ padding: '12px', color: 'var(--text-sub)' }}>{b.id}</td>
                  <td style={{ padding: '12px', fontWeight: '600' }}>{b.type}</td>
                  <td className="font-mono" style={{ padding: '12px', fontWeight: '700', color: b.color }}>{b.trigger}</td>
                  <td className="font-mono" style={{ padding: '12px' }}>{b.amount}</td>
                  <td className="font-mono" style={{ padding: '12px', fontWeight: '700', color: b.color }}>{b.rLevel}</td>
                  <td style={{ padding: '12px' }}>
                    <span className="badge badge-green" style={{ fontSize: '10px' }}>{b.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Execution Quality & Slippage Diagnostics */}
        <div className="glass-panel" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Crosshair size={18} color="#10B981" />
            <h3 style={{ fontSize: '16px', fontWeight: '700' }}>Execution Router Metrics</h3>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '12px', color: 'var(--text-sub)' }}>Routing Exchange</span>
              <span style={{ fontSize: '13px', fontWeight: '600' }}>Binance USDT-M Futures</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '12px', color: 'var(--text-sub)' }}>Execution Order Mode</span>
              <span style={{ fontSize: '13px', fontWeight: '600', color: '#10B981' }}>Smart Limit / Taker Fallback</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '12px', color: 'var(--text-sub)' }}>Simulated Slippage</span>
              <span className="font-mono" style={{ fontSize: '13px', fontWeight: '600', color: '#60A5FA' }}>1.8 bps ($0.61)</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '12px', color: 'var(--text-sub)' }}>Commission Paid</span>
              <span className="font-mono" style={{ fontSize: '13px', fontWeight: '600', color: 'var(--text-main)' }}>$1.35 (Maker 0.02%, Taker 0.04%)</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px' }}>
              <span style={{ fontSize: '12px', color: 'var(--text-sub)' }}>Fill Latency</span>
              <span className="font-mono" style={{ fontSize: '13px', fontWeight: '600', color: '#10B981' }}>18ms (Direct API)</span>
            </div>
          </div>
        </div>

      </div>

    </div>
  );
}
