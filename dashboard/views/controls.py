"""Manual Operator Controls View for the StrategyOne Streamlit Dashboard."""

from typing import Any, Dict
from loguru import logger
import streamlit as st

from core.events import (
    EVENT_CIRCUIT_BREAKER_TRIPPED,
    EVENT_EMERGENCY_FLATTEN,
    EVENT_VOLATILITY_REGIME_CHANGE,
    event_bus,
)


def render_controls_view(snapshot: Dict[str, Any]) -> None:
    """Renders manual interactive operator overrides and circuit breaker controls."""
    st.subheader("🕹️ Manual Operator Cockpit & Emergency Controls")
    st.caption("Direct command interface for institutional risk management and out-of-band system actions.")

    c1, c2, c3 = st.columns(3)

    with c1:
        with st.container(border=True):
            st.markdown("##### 🚨 Emergency Market Liquidation")
            st.write("Liquidates **all** open inventory at market and cancels resting brackets immediately.")
            if st.button("🔥 EMERGENCY FLATTEN ALL", type="primary", use_container_width=True):
                event_bus.publish(EVENT_EMERGENCY_FLATTEN, None)
                st.toast("🚨 Emergency Flatten Event Dispatched to TradeExecutionAgent!", icon="⚠️")
                logger.critical("OperatorDashboard: Manual EMERGENCY_FLATTEN triggered from UI.")

    with c2:
        with st.container(border=True):
            st.markdown("##### 🛑 Risk Circuit Breaker")
            st.write("Trips system circuit breaker to halt new trade entries and enforce risk cooldown.")
            if st.button("⚡ TRIP CIRCUIT BREAKER", use_container_width=True):
                event_bus.publish(EVENT_CIRCUIT_BREAKER_TRIPPED, "Manual Operator Override via Dashboard")
                st.toast("🛑 Circuit Breaker Tripped! System entries suspended.", icon="🛑")
                logger.warning("OperatorDashboard: Circuit breaker tripped by operator.")

    with c3:
        with st.container(border=True):
            st.markdown("##### 🧬 Force GA Population Retrain")
            st.write("Forces an out-of-band Genetic Algorithm evolution cycle across all 4 strategy species.")
            if st.button("🔄 RETRAIN GA POPULATION", use_container_width=True):
                event_bus.publish(EVENT_VOLATILITY_REGIME_CHANGE, "MANUAL_OPERATOR_TRIGGER")
                st.toast("🧬 GA Retraining Queued for Next Cycle!", icon="🧬")
                logger.info("OperatorDashboard: Manual GA retraining trigger dispatched.")
