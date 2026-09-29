"""Main Streamlit Application for StrategyOne Autonomous Multi-Agent Trading System."""

import sys
from pathlib import Path

# Add project root to sys.path so imports work seamlessly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from dashboard.state_reader import DashboardStateReader
from dashboard.views.backtest import render_backtest_view
from dashboard.views.boardroom import render_boardroom_view
from dashboard.views.controls import render_controls_view
from dashboard.views.positions import render_positions_view
from dashboard.views.risk import render_risk_view

# Streamlit Page Config
st.set_page_config(
    page_title="StrategyOne | Autonomous Multi-Agent Trading Cockpit",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom High-Aesthetic Styling
st.markdown(
    """
    <style>
    .main {
        background-color: #0b0e14;
    }
    .metric-card {
        background: rgba(22, 27, 34, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 16px;
    }
    header {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)


def main() -> None:
    # State reader initialization
    reader = DashboardStateReader()
    snapshot = reader.get_system_snapshot()

    # Sidebar
    with st.sidebar:
        st.title("🚀 StrategyOne")
        st.caption("Autonomous Quantitative Crypto Trading System")
        st.markdown("---")

        auto_refresh = st.checkbox("⚡ Live Auto-Refresh (3s)", value=False)
        if st.button("🔄 Refresh Snapshot Now", use_container_width=True):
            st.rerun()

        st.markdown("---")
        st.markdown("### ⚙️ System Profile")
        st.write("**Asset:** BTC/USDT")
        st.write("**Timeframes:** 15m (Primary), 1h, 4h, 1d")
        st.write("**Execution Engine:** High-Fidelity Paper / CCXT")
        st.write("**Committee Size:** 9 Autonomous Agents")
        st.caption(f"Last Checkpoint: {snapshot['orchestrator'].get('timestamp', 'N/A')}")

    # Header Title Banner
    header_col, status_col = st.columns([4, 1])
    with header_col:
        st.title("🎛️ StrategyOne Institutional Cockpit")
        st.caption("Real-Time Multi-Agent Committee Monitoring, Position Ladder & Risk Governance")
    with status_col:
        st.metric("System Mode", "LIVE DAEMON", delta="RUNNING", delta_color="normal")

    st.markdown("---")

    # Navigation Tabs
    tab_boardroom, tab_positions, tab_risk, tab_backtest, tab_controls = st.tabs([
        "🏛️ Committee Boardroom",
        "🪜 Active Positions & Brackets",
        "🛡️ Risk & Portfolio Governance",
        "📊 Backtest & Analytics",
        "🕹️ Operator Overrides",
    ])

    with tab_boardroom:
        render_boardroom_view(snapshot)

    with tab_positions:
        render_positions_view(snapshot)

    with tab_risk:
        render_risk_view(snapshot)

    with tab_backtest:
        render_backtest_view(snapshot)

    with tab_controls:
        render_controls_view(snapshot)

    # Optional Auto-refresh
    if auto_refresh:
        import time
        time.sleep(3)
        st.rerun()


if __name__ == "__main__":
    main()
