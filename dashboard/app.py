"""Interactive SADE-IoV dashboard (Section 5.8).

A Streamlit app that visualises live security-state transitions as telemetry is
perturbed. Move the sliders to inject jamming (RSSI collapse), flooding
(alpha_freq spike) or spoofing (velocity variance), change the payload class or
the user policy, and watch the orchestrator escalate / de-escalate in real time.

Run with:
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import streamlit as st

from sade_iov import config
from sade_iov.data_generator import generate_dataset
from sade_iov.decision_logic import execute_security_orchestration, explain
from sade_iov.risk_engine import RiskEngine, train_risk_engine

STATE_COLORS = {
    config.STATE_0_LOW: "#2ca02c",
    config.STATE_1_MEDIUM: "#ff7f0e",
    config.STATE_2_HIGH: "#d62728",
    config.STATE_3_CRITICAL: "#7f0000",
}


@st.cache_resource(show_spinner="Training risk engine...")
def get_engine() -> RiskEngine:
    if os.path.exists(config.MODEL_PATH) and os.path.exists(config.SCALER_PATH):
        try:
            return RiskEngine.load()
        except Exception:
            pass
    df = generate_dataset(n_epochs=6000)
    engine, _ = train_risk_engine(df)
    return engine


def main() -> None:
    st.set_page_config(page_title="SADE-IoV Orchestrator", layout="wide")
    st.title("SADE-IoV — Situation-Aware Dynamic Encryption")
    st.caption("Live adaptive-security orchestration for the Internet of Vehicles")

    engine = get_engine()

    with st.sidebar:
        st.header("Context inputs (F_t)")
        r_rssi = st.slider("R_RSSI — link strength (dBm)", -110.0, -40.0, -60.0, 1.0,
                           help="Sudden drops indicate jamming/spoofing.")
        v_var = st.slider("V_var — velocity variance", 0.0, 12.0, 0.5, 0.1,
                          help="Erratic jumps indicate ECU compromise/spoofing.")
        alpha = st.slider("alpha_freq — packet arrival rate", 0.0, 70.0, 10.0, 0.5,
                          help="Spikes indicate flooding/injection.")
        d_class = st.selectbox(
            "D_class — payload sensitivity",
            [config.DCLASS_INFOTAINMENT, config.DCLASS_LOCALISATION, config.DCLASS_SAFETY],
            format_func=lambda d: {0: "0 — infotainment", 1: "1 — localisation",
                                   2: "2 — safety-control"}[d],
        )
        policy = st.radio("User policy", [config.POLICY_STANDARD, config.POLICY_MAX_PRIVACY])

        st.divider()
        st.subheader("Quick attack presets")
        cols = st.columns(2)
        if cols[0].button("RF jamming"):
            st.session_state.update(preset=("jam"))
        if cols[1].button("Flooding"):
            st.session_state.update(preset=("flood"))

    s_risk = engine.score_epoch(r_rssi, v_var, alpha)
    state = execute_security_orchestration(s_risk, int(d_class), policy)
    proba = engine.predict_proba([[r_rssi, v_var, alpha]])[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Situational risk S_risk", f"{s_risk:.0f} / 100")
    c2.metric("Security state", config.STATE_NAMES[state].replace("STATE_", "").replace("_", " "))
    c3.metric("Cipher / key", "—" if state == config.STATE_3_CRITICAL
              else ("AES-128" if state == config.STATE_0_LOW else "AES-256"))

    st.markdown(
        f"<div style='padding:14px;border-radius:8px;background:{STATE_COLORS[state]};"
        f"color:white;font-weight:600'>{config.STATE_LABELS[state]}</div>",
        unsafe_allow_html=True,
    )
    st.write("**Decision rationale:**", explain(s_risk, int(d_class), policy))

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Misbehaviour-class probabilities")
        prob_df = pd.DataFrame({
            "class": [config.LABEL_TO_PROFILE[i] for i in range(len(proba))],
            "probability": proba,
        }).set_index("class")
        st.bar_chart(prob_df)

    with right:
        st.subheader("Risk-to-state mapping")
        risks = np.arange(0, 101)
        states = [execute_security_orchestration(float(r), int(d_class), policy) for r in risks]
        map_df = pd.DataFrame({"S_risk": risks, "state": states}).set_index("S_risk")
        st.line_chart(map_df)
        st.caption("Thresholds: 40 → MEDIUM, 85 → HIGH, 95 → CRITICAL "
                   "(D_class=2 floor forces HIGH above 50).")

    st.divider()
    st.subheader("Why this is fail-secure")
    st.markdown(
        "- The most severe condition is evaluated **first**, so the Critical "
        "state is always reachable.\n"
        "- A safety-control payload (`D_class=2`) imposes a **hard floor**: a "
        "benign risk score cannot downgrade it below HIGH.\n"
        "- The user policy can only **raise** the state, never lower it — "
        "neutralising downgrade attacks."
    )


if __name__ == "__main__":
    main()
