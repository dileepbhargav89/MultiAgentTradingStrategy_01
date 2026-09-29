import React, { useState, useEffect } from 'react';
import { 
  Briefcase, Network, Crosshair, BarChart3, Building2, 
  Terminal, Sparkles, RefreshCw, Layers, TrendingUp
} from 'lucide-react';
import CustomerBusinessHub from './components/CustomerBusinessHub';
import AgentNetwork from './components/AgentNetwork';
import PositionLadder from './components/PositionLadder';
import BacktestWorkbench from './components/BacktestWorkbench';
import InstitutionalSuite from './components/InstitutionalSuite';

export default function App() {
  const [activeTab, setActiveTab] = useState('business');
  const [btcPrice, setBtcPrice] = useState(65120.45);
  const [currentTime, setCurrentTime] = useState(new Date().toUTCString());

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date().toUTCString());
      // Subtle tick jitter for alive market feel
      setBtcPrice(prev => +(prev + (Math.random() - 0.48) * 1.5).toFixed(2));
    }, 1500);
    return () => clearInterval(timer);
  }, []);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      
      {/* Top Global Navigation Bar */}
      <header style={{ 
        height: '68px', 
        borderBottom: '1px solid var(--border-color)', 
        background: 'rgba(11, 15, 23, 0.85)', 
        backdropFilter: 'blur(16px)', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between', 
        padding: '0 28px',
        position: 'sticky',
        top: 0,
        zIndex: 100
      }}>
        {/* Brand & Mode */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }} onClick={() => setActiveTab('business')}>
            <div style={{ 
              width: '36px', 
              height: '36px', 
              borderRadius: '8px', 
              background: 'linear-gradient(135deg, #2563EB, #10B981)', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              boxShadow: '0 0 16px rgba(37, 99, 235, 0.4)'
            }}>
              <Terminal size={20} color="#FFF" />
            </div>
            <div>
              <div style={{ fontSize: '16px', fontWeight: '900', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '8px' }}>
                STRATEGY<span style={{ color: '#3B82F6' }}>ONE</span>
                <span className="badge badge-green" style={{ fontSize: '10px' }}>v2.0 PRO</span>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', letterSpacing: '0.04em' }}>
                AUTONOMOUS QUANT TRADING COCKPIT
              </div>
            </div>
          </div>

          <div style={{ height: '24px', width: '1px', background: 'var(--border-color)', margin: '0 8px' }}></div>

          {/* System Health Badge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 12px', background: 'rgba(16, 185, 129, 0.08)', borderRadius: '6px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
            <span className="live-indicator"></span>
            <span style={{ fontSize: '12px', fontWeight: '700', color: '#34D399' }}>DAEMON ONLINE</span>
            <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>(9 Agents Synced)</span>
          </div>
        </div>

        {/* Center: Interactive Tab Switcher */}
        <div style={{ display: 'flex', background: 'rgba(255, 255, 255, 0.03)', padding: '4px', borderRadius: '10px', border: '1px solid var(--border-color)', gap: '4px' }}>
          
          <button 
            onClick={() => setActiveTab('business')}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '7px', 
              padding: '8px 15px', 
              borderRadius: '8px', 
              border: 'none', 
              background: activeTab === 'business' ? 'linear-gradient(135deg, #2563EB, #1D4ED8)' : 'transparent',
              color: activeTab === 'business' ? '#FFFFFF' : 'var(--text-sub)',
              fontSize: '13px',
              fontWeight: '700',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              boxShadow: activeTab === 'business' ? '0 4px 12px rgba(37, 99, 235, 0.35)' : 'none'
            }}
          >
            <Briefcase size={15} />
            Executive Hub
          </button>

          <button 
            onClick={() => setActiveTab('agents')}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '7px', 
              padding: '8px 15px', 
              borderRadius: '8px', 
              border: 'none', 
              background: activeTab === 'agents' ? '#2563EB' : 'transparent',
              color: activeTab === 'agents' ? '#FFFFFF' : 'var(--text-sub)',
              fontSize: '13px',
              fontWeight: '700',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              boxShadow: activeTab === 'agents' ? '0 4px 12px rgba(37, 99, 235, 0.35)' : 'none'
            }}
          >
            <Network size={15} />
            Agent Consensus
          </button>

          <button 
            onClick={() => setActiveTab('execution')}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '7px', 
              padding: '8px 15px', 
              borderRadius: '8px', 
              border: 'none', 
              background: activeTab === 'execution' ? '#2563EB' : 'transparent',
              color: activeTab === 'execution' ? '#FFFFFF' : 'var(--text-sub)',
              fontSize: '13px',
              fontWeight: '700',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              boxShadow: activeTab === 'execution' ? '0 4px 12px rgba(37, 99, 235, 0.35)' : 'none'
            }}
          >
            <Crosshair size={15} />
            Execution & Ladder
          </button>

          <button 
            onClick={() => setActiveTab('backtest')}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '7px', 
              padding: '8px 15px', 
              borderRadius: '8px', 
              border: 'none', 
              background: activeTab === 'backtest' ? '#2563EB' : 'transparent',
              color: activeTab === 'backtest' ? '#FFFFFF' : 'var(--text-sub)',
              fontSize: '13px',
              fontWeight: '700',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              boxShadow: activeTab === 'backtest' ? '0 4px 12px rgba(37, 99, 235, 0.35)' : 'none'
            }}
          >
            <BarChart3 size={15} />
            2-Year Backtest
          </button>

          <button 
            onClick={() => setActiveTab('institutional')}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '7px', 
              padding: '8px 15px', 
              borderRadius: '8px', 
              border: 'none', 
              background: activeTab === 'institutional' ? '#10B981' : 'transparent',
              color: activeTab === 'institutional' ? '#064E3B' : 'var(--text-sub)',
              fontSize: '13px',
              fontWeight: '700',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              boxShadow: activeTab === 'institutional' ? '0 4px 12px rgba(16, 185, 129, 0.35)' : 'none'
            }}
          >
            <Building2 size={15} />
            Institutional Suite
          </button>
        </div>

        {/* Right: Live Market Ticker & UTC Clock */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '18px' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'flex-end' }}>
              <span style={{ fontSize: '11px', color: 'var(--text-dim)', textTransform: 'uppercase' }}>BTC/USDT Mark</span>
              <span className="badge badge-amber" style={{ fontSize: '9px', padding: '1px 6px' }}>BULL TREND</span>
            </div>
            <div className="font-mono" style={{ fontSize: '17px', fontWeight: '800', color: '#60A5FA' }}>
              ${btcPrice.toLocaleString()}
            </div>
          </div>

          <div style={{ height: '24px', width: '1px', background: 'var(--border-color)' }}></div>

          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '11px', color: 'var(--text-dim)', textTransform: 'uppercase' }}>UTC Telemetry</div>
            <div className="font-mono" style={{ fontSize: '12px', color: 'var(--text-sub)' }}>
              {currentTime.slice(17, 25)}
            </div>
          </div>
        </div>
      </header>

      {/* Main App Content View */}
      <main style={{ flex: 1, padding: '24px 28px', maxWidth: '1680px', width: '100%', margin: '0 auto' }}>
        {activeTab === 'business' && <CustomerBusinessHub onSelectTab={setActiveTab} />}
        {activeTab === 'agents' && <AgentNetwork />}
        {activeTab === 'execution' && <PositionLadder />}
        {activeTab === 'backtest' && <BacktestWorkbench />}
        {activeTab === 'institutional' && <InstitutionalSuite />}
      </main>

      {/* Footer Info */}
      <footer style={{ 
        borderTop: '1px solid var(--border-color)', 
        padding: '14px 28px', 
        fontSize: '12px', 
        color: 'var(--text-dim)', 
        display: 'flex', 
        justifyContent: 'space-between',
        background: 'rgba(11, 15, 23, 0.6)'
      }}>
        <div>StrategyOne Autonomous Multi-Agent Trading System | CCXT Testnet Engine</div>
        <div style={{ display: 'flex', gap: '16px' }}>
          <span>Feed: Binance USDT-M Perpetual</span>
          <span>Risk Engine: Cornish-Fisher VaR (95%)</span>
          <span>Governance: Macro 200 SMA Gate</span>
        </div>
      </footer>

    </div>
  );
}
