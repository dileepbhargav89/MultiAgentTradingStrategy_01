"""Visual Boardroom View for the StrategyOne Streamlit Dashboard.

Renders the multi-agent committee status, consensus voting gauge, and
real-time agent breakdown with institutional aesthetic cards and status badges.
"""

from typing import Any, Dict
import streamlit as st


def render_boardroom_view(snapshot: Dict[str, Any]) -> None:
    """Renders the 9-Agent Autonomous Committee Boardroom view."""
    st.subheader("🏛️ Multi-Agent Autonomous Committee Boardroom")

    orch = snapshot["orchestrator"]
    agent_states = orch.get("agent_states", {})
    champion = orch.get("champion", {})

    # Top metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="Cycle Count",
            value=f"#{orch.get('cycle_count', 0)}",
            help="Total decision cycles executed since system inception.",
        )
    with col2:
        dq_status = agent_states.get("data_quality", "HEALTHY")
        st.metric(
            label="Data Quality Gate",
            value=dq_status,
            delta="PASS" if dq_status == "HEALTHY" else "VETO HALT",
            delta_color="normal" if dq_status == "HEALTHY" else "inverse",
            help="Data Quality Agent has absolute veto power over trading cycles.",
        )
    with col3:
        risk_tier = agent_states.get("risk_tier", "GREEN")
        st.metric(
            label="Risk Governance Tier",
            value=risk_tier,
            delta="Normal Operations" if risk_tier == "GREEN" else "Constrained",
            delta_color="normal" if risk_tier == "GREEN" else "inverse",
            help="5-tier risk drawdown state machine with hysteresis deadbands.",
        )
    with col4:
        champ_id = champion.get("strategy_id", "MOM-DEFAULT")
        species = champion.get("species", "MOMENTUM_TREND")
        st.metric(
            label="Active Champion DNA",
            value=champ_id,
            delta=species,
            help="Active GA champion strategy evolved by Strategy Evolution Agent.",
        )

    st.markdown("---")

    # 9-Agent Committee Status Grid
    st.markdown("#### 👥 9-Agent Committee Roster & Health")
    agents_info = [
        {"num": "1", "name": "Data Quality Agent", "role": "Data Ingestion & Integrity Audit", "status": agent_states.get("data_quality", "HEALTHY"), "veto": "ABSOLUTE VETO"},
        {"num": "2", "name": "Technical Agent", "role": "Multi-TF Confluence (15m, 1h, 4h, 1d)", "status": "ACTIVE", "veto": "None"},
        {"num": "3", "name": "Market Agent", "role": "Derivatives, Funding Z-Score & Sentiment", "status": "ACTIVE", "veto": "Warning"},
        {"num": "4", "name": "Volatility Agent", "role": "GARCH, EWMA, Parkinson & Regime", "status": "ACTIVE", "veto": "None"},
        {"num": "5", "name": "Strategy Evolver", "role": "4-Species Genetic Algorithm Evolution", "status": f"Champion: {champ_id}", "veto": "None"},
        {"num": "6", "name": "Risk Agent", "role": "Cornish-Fisher VaR & 7-Gate Audit", "status": f"Tier: {risk_tier}", "veto": "ABSOLUTE VETO"},
        {"num": "7", "name": "Money Agent", "role": "Half-Kelly Sizing & 40% Reserve", "status": "ACTIVE", "veto": "None"},
        {"num": "8", "name": "Trade Decider", "role": "3-Layer Gatekeeper & Boardroom Vote", "status": "CONSENSUS >= 65%", "veto": "FINAL JUDGE"},
        {"num": "9", "name": "Trade Executor", "role": "Multi-Tier Brackets & OCO Ratcheting", "status": agent_states.get("execution_agent", "IDLE"), "veto": "None"},
    ]

    c_left, c_right = st.columns(2)
    for i, a in enumerate(agents_info):
        col = c_left if i % 2 == 0 else c_right
        with col:
            with st.container(border=True):
                head_col, status_col = st.columns([3, 1])
                with head_col:
                    st.markdown(f"**Agent #{a['num']}: {a['name']}**")
                    st.caption(a["role"])
                with status_col:
                    if "VETO" in a["veto"]:
                        st.badge("🛡️ VETO GATE")
                    st.code(a["status"], language="text")
