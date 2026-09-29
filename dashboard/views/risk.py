"""Portfolio Equity, Drawdown & Risk Governance View for the StrategyOne Streamlit Dashboard."""

from typing import Any, Dict, List
import pandas as pd
import streamlit as st


def render_risk_view(snapshot: Dict[str, Any]) -> None:
    """Renders portfolio equity, mark-to-market drawdown, and risk governance limits."""
    st.subheader("🛡️ Portfolio Equity & Institutional Risk Governance")

    port = snapshot.get("portfolio", {})
    cash = port.get("current_cash", 10000.0)
    hwm = port.get("high_water_mark", 10000.0)
    dd_pct = port.get("drawdown_pct", 0.0)
    realized_pnl = port.get("realized_pnl_cumulative", 0.0)

    # 1. Financial KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="Current Cash Balance",
            value=f"${cash:,.2f}",
            delta=f"${realized_pnl:+,.2f} Realized PnL",
            delta_color="normal" if realized_pnl >= 0 else "inverse",
        )
    with col2:
        st.metric(
            label="Peak High Water Mark (HWM)",
            value=f"${hwm:,.2f}",
            help="All-time highest recorded portfolio mark-to-market equity.",
        )
    with col3:
        st.metric(
            label="Peak-to-Trough Drawdown",
            value=f"{dd_pct:.2%}",
            delta="-10.0% Max Cap",
            delta_color="inverse" if dd_pct > 0.04 else "normal",
            help="Current drawdown vs all-time high water mark.",
        )
    with col4:
        consec_losses = port.get("consecutive_losses", 0)
        cooldown = port.get("is_cooldown_active", False)
        st.metric(
            label="Consecutive Losses",
            value=f"{consec_losses} / 3",
            delta="2h Cooldown Active" if cooldown else "Normal Trading",
            delta_color="inverse" if cooldown else "normal",
        )

    st.markdown("---")

    # 2. Horizon Limits & Loss Thresholds
    st.markdown("#### ⏳ Calendar Loss Limits & Safety Deadbands")
    c1, c2, c3 = st.columns(3)
    with c1:
        daily_loss = port.get("daily_loss_pct", 0.0)
        st.write(f"**Daily Loss (UTC Midnight)**: `{daily_loss:.2%}` / `-3.00%`")
        st.progress(min(daily_loss / 0.03, 1.0))
    with c2:
        weekly_loss = port.get("weekly_loss_pct", 0.0)
        st.write(f"**Weekly Loss (Monday UTC)**: `{weekly_loss:.2%}` / `-6.00%`")
        st.progress(min(weekly_loss / 0.06, 1.0))
    with c3:
        st.write(f"**Max Portfolio Drawdown**: `{dd_pct:.2%}` / `-10.00%`")
        st.progress(min(dd_pct / 0.10, 1.0))

    st.markdown("---")

    # 3. Trade History Audit Log
    st.markdown("#### 📜 Executed Trade History & Realized PnL")
    history: List[Dict[str, Any]] = port.get("trade_history", [])
    if not history:
        st.caption("No closed trades recorded yet.")
    else:
        hist_rows = []
        for t in reversed(history[-50:]):
            hist_rows.append({
                "Timestamp": t.get("timestamp", ""),
                "Order ID": t.get("order_id", ""),
                "Symbol": t.get("symbol", ""),
                "Side": t.get("side", ""),
                "Fill Price": f"${t.get('fill_price', 0.0):,.2f}",
                "Quantity": f"{t.get('quantity', 0.0):.6f}",
                "Realized PnL ($)": f"${t.get('realized_pnl_usd', 0.0):+,.2f}",
                "Exit Reason": t.get("reason", "N/A"),
            })
        df_hist = pd.DataFrame(hist_rows)
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
