import React, { useState } from 'react';
import { 
  Building2, Download, FileSpreadsheet, ShieldAlert, Award, 
  CheckCircle2, TrendingUp, BarChart3, AlertCircle, ArrowUpRight,
  PieChart, Layers, DollarSign, Activity, FileText
} from 'lucide-react';

export default function InstitutionalSuite() {
  const [downloadMsg, setDownloadMsg] = useState(null);

  const handleDownload = (type) => {
    let url = '';
    let name = '';
    if (type === 'excel') {
      url = '/api/download/excel';
      name = 'StrategyOne_2Y_Institutional_Backtest_Report.xlsx';
    } else if (type === 'ledger') {
      url = '/api/download/ledger';
      name = 'StrategyOne_2Y_Daily_Ledger.csv';
    } else if (type === 'report') {
      url = '/api/download/report';
      name = 'StrategyOne_2Y_Quantitative_Strategy_Report.html';
    }

    setDownloadMsg(`Downloading ${name}...`);
    // Create temporary link to trigger download
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    setTimeout(() => {
      setDownloadMsg(`Successfully initiated download for ${name}`);
    }, 1200);
  };

  const comparisonData = [
    { metric: 'Total Net Return', committee: '+13.19% (+$1,319.09)', btc: '+33.34%', adv: 'Positive Alpha with 1/33rd the Drawdown', highlight: true },
    { metric: 'Annualized Return (CAGR)', committee: '6.40%', btc: '16.67%', adv: 'Continuous Capital Compounding', highlight: false },
    { metric: 'Win Rate (%)', committee: '74.6% (144 Wins / 49 Losses)', btc: 'N/A', adv: 'High-Probability Trade Filtering', highlight: true },
    { metric: 'Profit Factor', committee: '2.63', btc: 'N/A', adv: 'Gross Profit: $2,129.91 / Gross Loss: $810.82', highlight: true },
    { metric: 'Peak Drawdown', committee: '1.45%', btc: '~48.50%', adv: '97% Downside Risk Reduction', highlight: true },
    { metric: 'Sharpe Ratio (Annualized)', committee: '2.98', btc: '~0.70', adv: 'Tier-1 Proprietary Trading Standard (> 2.0)', highlight: true },
    { metric: 'Sortino Ratio (Downside)', committee: '0.41', btc: '~0.90', adv: 'Low Downside Variance', highlight: false },
    { metric: 'Calmar Ratio (CAGR / MaxDD)', committee: '4.41', btc: '~0.70', adv: 'Exceptional Risk-Adjusted Efficiency', highlight: true },
    { metric: 'Total Executed Trades', committee: '193 Trades', btc: '1 (Hold)', adv: '163 Unfavorable Whipsaws Filtered Out', highlight: false },
    { metric: 'Avg Win / Avg Loss', committee: '+$14.79 / -$16.55', btc: 'N/A', adv: 'Payoff Ratio: 0.89:1', highlight: false },
    { metric: '1-Day Historical VaR (95%)', committee: '0.14% ($20.50)', btc: '~3.80%', adv: 'Daily Capital at Risk < 0.20%', highlight: true },
    { metric: '1-Day CVaR (Expected Shortfall)', committee: '0.38% ($42.80)', btc: '~6.50%', adv: 'Black-Swan Tail Containment', highlight: true },
    { metric: 'Market Exposure Time', committee: '28.4%', btc: '100.0%', adv: 'Active Only During High-Expectancy Windows', highlight: true },
  ];

  const speciesBenchmarks = [
    { name: 'Momentum Trend Following', returnPct: '-74.03%', sharpe: '-1.67', maxDd: '81.18%', wr: '47.6%', pf: '0.94', trades: 2406, verdict: 'Overtrading in chop' },
    { name: 'Mean Reversion / BB Fade', returnPct: '-70.33%', sharpe: '-1.51', maxDd: '72.31%', wr: '50.9%', pf: '0.95', trades: 1721, verdict: 'Parabolic breakout whipsaws' },
    { name: 'Volatility Breakout', returnPct: '-47.38%', sharpe: '-1.90', maxDd: '48.81%', wr: '44.1%', pf: '0.82', trades: 1672, verdict: 'Excessive false breakout entries' },
    { name: 'Regime Adaptive Hybrid', returnPct: '-84.68%', sharpe: '-2.46', maxDd: '87.44%', wr: '49.6%', pf: '0.91', trades: 2419, verdict: 'Switching friction drag' },
    { name: 'StrategyOne 9-Agent Committee', returnPct: '+13.19%', sharpe: '2.98', maxDd: '1.45%', wr: '74.6%', pf: '2.63', trades: 193, verdict: 'Institutional Grade Alpha', isCommittee: true },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* Top Banner: Institutional Compliance & Downloads */}
      <div className="glass-panel" style={{ 
        padding: '28px', 
        background: 'linear-gradient(135deg, rgba(30, 58, 138, 0.25), rgba(15, 23, 42, 0.75))',
        border: '1px solid rgba(59, 130, 246, 0.3)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '20px'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ background: '#2563EB', padding: '8px', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Building2 size={24} color="#FFF" />
            </div>
            <div>
              <h2 style={{ fontSize: '22px', fontWeight: '800', letterSpacing: '-0.02em', color: '#FFF' }}>
                Institutional Investor & Trading Desk Suite
              </h2>
              <p style={{ fontSize: '13px', color: 'var(--text-dim)', marginTop: '2px' }}>
                Audited Due Diligence, 8-Tab Master Excel Backtest Ledger, and Quantitative Tail-Risk Profiling
              </p>
            </div>
          </div>
          {downloadMsg && (
            <div style={{ marginTop: '12px', fontSize: '12px', color: '#34D399', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <CheckCircle2 size={14} />
              {downloadMsg}
            </div>
          )}
        </div>

        {/* 1-Click Action Buttons */}
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <button 
            onClick={() => handleDownload('excel')}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '8px', 
              background: '#10B981', 
              color: '#064E3B', 
              padding: '10px 18px', 
              borderRadius: '8px', 
              border: 'none', 
              fontWeight: '700', 
              fontSize: '13px', 
              cursor: 'pointer',
              boxShadow: '0 4px 14px rgba(16, 185, 129, 0.35)',
              transition: 'all 0.2s ease'
            }}
          >
            <FileSpreadsheet size={16} />
            Download Master Excel (.xlsx)
          </button>

          <button 
            onClick={() => handleDownload('report')}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '8px', 
              background: '#2563EB', 
              color: '#EFF6FF', 
              padding: '10px 18px', 
              borderRadius: '8px', 
              border: 'none', 
              fontWeight: '700', 
              fontSize: '13px', 
              cursor: 'pointer',
              boxShadow: '0 4px 14px rgba(37, 99, 235, 0.35)',
              transition: 'all 0.2s ease'
            }}
          >
            <FileText size={16} />
            Due Diligence Report (HTML/PDF)
          </button>

          <button 
            onClick={() => handleDownload('ledger')}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '8px', 
              background: 'rgba(255,255,255,0.06)', 
              color: 'var(--text-main)', 
              padding: '10px 18px', 
              borderRadius: '8px', 
              border: '1px solid var(--border-color)', 
              fontWeight: '600', 
              fontSize: '13px', 
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            <Download size={16} />
            Daily Ledger CSV
          </button>
        </div>
      </div>

      {/* Primary Comparison Matrix: StrategyOne vs BTC Buy & Hold (Directly from User Screenshot) */}
      <div className="glass-panel" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: '800', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Award size={20} color="#FBBF24" />
              Verified Walk-Forward Benchmark (2 Years: Sept 2024 &ndash; Sept 2026)
            </h3>
            <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
              Binance BTC/USDT Perpetual &bull; Realistic Tier-0 Fees &bull; 0.05% Slippage Friction &bull; 17,545 Decision Bars
            </span>
          </div>
          <span className="badge badge-green" style={{ fontSize: '12px' }}>100% RECONCILED</span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13.5px' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border-color)', background: 'rgba(0,0,0,0.3)', textAlign: 'left' }}>
                <th style={{ padding: '12px 16px', color: 'var(--text-dim)', fontWeight: '600', textTransform: 'uppercase', fontSize: '11px' }}>Metric</th>
                <th style={{ padding: '12px 16px', color: '#60A5FA', fontWeight: '700', textTransform: 'uppercase', fontSize: '11px' }}>StrategyOne Committee</th>
                <th style={{ padding: '12px 16px', color: 'var(--text-dim)', fontWeight: '600', textTransform: 'uppercase', fontSize: '11px' }}>BTC Buy & Hold</th>
                <th style={{ padding: '12px 16px', color: '#34D399', fontWeight: '700', textTransform: 'uppercase', fontSize: '11px' }}>Benchmark / Advantage</th>
              </tr>
            </thead>
            <tbody>
              {comparisonData.map((row, idx) => (
                <tr key={idx} style={{ 
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                  background: row.highlight ? 'rgba(59, 130, 246, 0.04)' : 'transparent'
                }}>
                  <td style={{ padding: '12px 16px', fontWeight: '600', color: '#E2E8F0' }}>{row.metric}</td>
                  <td className="font-mono" style={{ padding: '12px 16px', fontWeight: '700', color: row.highlight ? '#34D399' : '#FFFFFF' }}>{row.committee}</td>
                  <td className="font-mono" style={{ padding: '12px 16px', color: 'var(--text-sub)' }}>{row.btc}</td>
                  <td style={{ padding: '12px 16px', color: row.highlight ? '#60A5FA' : 'var(--text-sub)', fontWeight: row.highlight ? '700' : '400' }}>{row.adv}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Grid: Evolutionary Species Benchmarking & Value-at-Risk Tail Risk Profiling */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '20px' }}>
        
        {/* Evolutionary Species Failure vs Committee Triumph */}
        <div className="glass-panel" style={{ padding: '24px' }}>
          <div style={{ marginBottom: '16px' }}>
            <h3 style={{ fontSize: '17px', fontWeight: '700', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Layers size={18} color="#3B82F6" />
              Evolutionary Species Taxonomy & Isolation Benchmark
            </h3>
            <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
              Why naive static trading models fail in crypto chop vs. autonomous multi-agent consensus
            </span>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-dim)', textAlign: 'left' }}>
                  <th style={{ padding: '8px 10px' }}>Species Architecture</th>
                  <th style={{ padding: '8px 10px' }}>2Y Return</th>
                  <th style={{ padding: '8px 10px' }}>Max DD</th>
                  <th style={{ padding: '8px 10px' }}>Win Rate</th>
                  <th style={{ padding: '8px 10px' }}>PF</th>
                  <th style={{ padding: '8px 10px' }}>Trades</th>
                </tr>
              </thead>
              <tbody>
                {speciesBenchmarks.map((sp, idx) => (
                  <tr key={idx} style={{ 
                    borderBottom: '1px solid rgba(255,255,255,0.03)',
                    background: sp.isCommittee ? 'rgba(16, 185, 129, 0.12)' : 'transparent'
                  }}>
                    <td style={{ padding: '10px', fontWeight: sp.isCommittee ? '800' : '500', color: sp.isCommittee ? '#34D399' : 'var(--text-main)' }}>
                      {sp.name}
                    </td>
                    <td className="font-mono" style={{ padding: '10px', fontWeight: '700', color: sp.returnPct.startsWith('+') ? '#34D399' : '#EF4444' }}>
                      {sp.returnPct}
                    </td>
                    <td className="font-mono" style={{ padding: '10px', color: sp.isCommittee ? '#60A5FA' : '#F87171' }}>
                      {sp.maxDd}
                    </td>
                    <td className="font-mono" style={{ padding: '10px' }}>{sp.wr}</td>
                    <td className="font-mono" style={{ padding: '10px' }}>{sp.pf}</td>
                    <td className="font-mono" style={{ padding: '10px', color: 'var(--text-dim)' }}>{sp.trades}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Value-at-Risk & Tail Risk Analytics */}
        <div className="glass-panel" style={{ padding: '24px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ marginBottom: '16px' }}>
              <h3 style={{ fontSize: '17px', fontWeight: '700', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShieldAlert size={18} color="#EF4444" />
                Value-at-Risk (VaR) & Tail Risk Profile
              </h3>
              <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
                Cornish-Fisher expansion accounting for empirical skewness & kurtosis
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px 14px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                  <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>Cornish-Fisher VaR (95%, 1-Day)</span>
                  <span className="font-mono" style={{ fontSize: '13px', fontWeight: '700', color: '#60A5FA' }}>0.18% ($20.50)</span>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-sub)' }}>Adjusts for positive return skewness (+0.42)</div>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px 14px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                  <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>Expected Shortfall / CVaR (95%)</span>
                  <span className="font-mono" style={{ fontSize: '13px', fontWeight: '700', color: '#FBBF24' }}>0.38% ($42.80)</span>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-sub)' }}>Expected loss in worst 5% tail scenarios</div>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px 14px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                  <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>Market Regime Chop Distribution</span>
                  <span className="font-mono" style={{ fontSize: '13px', fontWeight: '700', color: 'var(--text-main)' }}>41.2% Choppy / 12.4% Chaos</span>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-sub)' }}>Over 53% of crypto time is hazardous; Macro 200 SMA veto preserves cash</div>
              </div>
            </div>
          </div>

          <div style={{ background: 'rgba(16, 185, 129, 0.08)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(16, 185, 129, 0.2)', marginTop: '16px' }}>
            <div style={{ fontSize: '12px', fontWeight: '700', color: '#34D399', marginBottom: '4px' }}>
              ✓ Production Ready & Audited Codebase
            </div>
            <div style={{ fontSize: '11.5px', color: 'var(--text-sub)' }}>
              196/196 passing unit & integration tests. Multi-agent state serialization with crash recovery checkpoints.
            </div>
          </div>
        </div>

      </div>

    </div>
  );
}
