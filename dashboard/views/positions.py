"""Positions and Bracket Orders Ladder View for the StrategyOne Streamlit Dashboard."""

from typing import Any, Dict, List
import pandas as pd
import streamlit as st


def render_positions_view(snapshot: Dict[str, Any]) -> None:
    """Renders active positions, unrealized PnL, and resting bracket orders ladder."""
    st.subheader("🪜 Active Inventory & Multi-Tier Bracket Ladder")

    positions: List[Dict[str, Any]] = snapshot.get("positions", [])
    brackets: List[Dict[str, Any]] = snapshot.get("brackets", [])

    if not positions:
        st.info("No open positions. System is monitoring the market or in cash reserve.")
    else:
        st.markdown("#### 📈 Open Positions")
        pos_rows = []
        for p in positions:
            pnl_usd = p.get("unrealized_pnl_usd", 0.0)
            pnl_pct = p.get("unrealized_pnl_pct", 0.0)
            be_status = "✅ YES" if p.get("is_breakeven_active") else "⏳ PENDING TP1"
            scale_status = "✅ 50% SCALED" if p.get("is_scale_out_executed") else "RUNNING 100%"

            pos_rows.append({
                "Position ID": p.get("position_id", ""),
                "Symbol": p.get("symbol", ""),
                "Side": p.get("side", ""),
                "Entry Price": f"${p.get('entry_price', 0.0):,.2f}",
                "Mark Price": f"${p.get('current_mark_price', p.get('entry_price', 0.0)):,.2f}",
                "Size (Asset)": f"{p.get('quantity', 0.0):.6f}",
                "Notional": f"${p.get('notional_usd', 0.0):,.2f}",
                "Unrealized PnL": f"${pnl_usd:+,.2f} ({pnl_pct:+.2%})",
                "Stop Loss": f"${p.get('stop_loss_price', 0.0):,.2f}",
                "TP1 (1.5R)": f"${p.get('take_profit_price_1', 0.0):,.2f}",
                "TP2 (2.5R)": f"${p.get('take_profit_price_2', 0.0):,.2f}",
                "Breakeven Ratchet": be_status,
                "Scale-Out": scale_status,
            })

        df_pos = pd.DataFrame(pos_rows)
        st.dataframe(df_pos, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Resting Brackets Section
    st.markdown("#### 🎯 Bracket Order Groups & OCO Linkage")
    if not brackets:
        st.caption("No resting bracket order structures currently active.")
    else:
        brk_rows = []
        for b in brackets:
            brk_rows.append({
                "Bracket ID": b.get("bracket_id", ""),
                "Parent Order ID": b.get("parent_order_id", ""),
                "Parent Status": b.get("parent_status", ""),
                "Stop Loss Order": b.get("stop_order_id", "N/A"),
                "Stop Status": b.get("stop_status", ""),
                "TP1 Order": b.get("tp1_order_id", "N/A"),
                "TP1 Status": b.get("tp1_status", ""),
                "TP2 Runner Order": b.get("tp2_order_id", "N/A"),
                "TP2 Status": b.get("tp2_status", ""),
                "OCO Mutual Active": "ACTIVE" if b.get("is_oco_active") else "TRIGGERED/OFF",
            })
        df_brk = pd.DataFrame(brk_rows)
        st.dataframe(df_brk, use_container_width=True, hide_index=True)
