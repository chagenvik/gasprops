"""
Phase Envelope tab for the Gas Properties module.

Uses neqsim to calculate dew-point and bubble-point curves,
cricondentherm, cricondenbar, and critical point for the given gas composition.
"""

import hashlib
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_NEQSIM_NAMES: dict[str, str] = {
    "N2":   "nitrogen",
    "CO2":  "CO2",
    "C1":   "methane",
    "C2":   "ethane",
    "C3":   "propane",
    "iC4":  "i-butane",
    "nC4":  "n-butane",
    "iC5":  "i-pentane",
    "nC5":  "n-pentane",
    "nC6":  "n-hexane",
    "nC7":  "n-heptane",
    "nC8":  "n-octane",
    "nC9":  "n-nonane",
    "nC10": "nC10",
    "H2O":  "water",
    "He":   "helium",
    "H2":   "hydrogen",
    "Ar":   "argon",
    "CO":   "CO",
    "O2":   "oxygen",
    "H2S":  "H2S",
}

_EOS_OPTIONS: dict[str, str] = {
    "SRK (Soave-Redlich-Kwong)": "srk",
    "PR (Peng-Robinson)": "pr",
    "UMR-PRU (recommended for HC dew point)": "pr-umr",
}


def _comp_hash(composition: dict, eos_label: str) -> str:
    """Return a stable cache hash for a composition and EoS."""
    payload = {"composition": composition, "eos": eos_label}
    return hashlib.md5(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _calculate(composition: dict, eos_label: str) -> dict:
    """Calculate phase-envelope data for the selected composition."""
    from neqsim.thermo import TPflash, fluid, phaseenvelope

    model = _EOS_OPTIONS[eos_label]
    model_name = eos_label

    total = sum(composition.values())
    norm = {k: v / total for k, v in composition.items() if v > 0.0}

    skipped = [c for c in norm if c not in _NEQSIM_NAMES]

    gas_fluid = fluid(model)
    for comp, frac in norm.items():
        if comp in _NEQSIM_NAMES:
            gas_fluid.addComponent(_NEQSIM_NAMES[comp], frac)

    gas_fluid.setTemperature(15.0, "C")
    gas_fluid.setPressure(1.0, "bara")
    gas_fluid.setMixingRule(2)
    TPflash(gas_fluid)

    env = phaseenvelope(gas_fluid, False)

    dew_T = [t - 273.15 for t in env.get("dewT")]
    dew_P = list(env.get("dewP"))
    bub_T = [t - 273.15 for t in env.get("bubT")]
    bub_P = list(env.get("bubP"))

    cct = env.get("cricondentherm")
    ccb = env.get("cricondenbar")

    critical_T = critical_P = None
    try:
        cp = env.get("criticalPoint1")
        if cp and len(cp) >= 2 and cp[1] > 0:
            critical_T = cp[0] - 273.15
            critical_P = float(cp[1])
    except Exception:
        st.toast("Warning: Failed to extract critical point from NeqSim results.", icon="⚠️")

    return {
        "dew_T": dew_T,
        "dew_P": dew_P,
        "bub_T": bub_T,
        "bub_P": bub_P,
        "cricondentherm_T": cct[0] - 273.15,
        "cricondentherm_P": cct[1],
        "cricondenbar_T":   ccb[0] - 273.15,
        "cricondenbar_P":   ccb[1],
        "critical_T":       critical_T,
        "critical_P":       critical_P,
        "model_name":       model_name,
        "skipped":          skipped,
    }


def render(composition: dict | None) -> None:
    """Render the Phase Envelope tab."""

    if composition is None:
        st.info("Enter a valid composition above to calculate the phase envelope.")
        return

    eos_label = st.selectbox(
        "Equation of State",
        options=list(_EOS_OPTIONS.keys()),
        index=0,
        key="phase_envelope_eos",
        help="UMR-PRU is recommended for accurate hydrocarbon dew-point calculations.",
    )

    st.caption("💡 Fluid composition will be normalised before simulation.")

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        calc_clicked = st.button(
            "Calculate Phase Envelope",
            type="primary",
            key="phase_envelope_calc_btn",
        )

    comp_hash = _comp_hash(composition, eos_label)
    cache_key = f"phase_envelope_result_{comp_hash}"

    if calc_clicked:
        with st.spinner("Calculating phase envelope …"):
            try:
                result = _calculate(composition, eos_label)
                st.session_state[cache_key] = result
            except Exception as exc:
                st.error(f"Calculation failed: {exc}")
                return

    result = st.session_state.get(cache_key)
    if result is None:
        return

    if result["skipped"]:
        st.warning(
            f"The following components have no neqsim mapping and were skipped: "
            f"{', '.join(result['skipped'])}"
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cricondentherm", f"{result['cricondentherm_T']:.1f} °C")
    m2.metric("Cricondentherm pressure", f"{result['cricondentherm_P']:.2f} bara")
    m3.metric("Cricondenbar", f"{result['cricondenbar_P']:.2f} bara")
    m4.metric("Cricondenbar temperature", f"{result['cricondenbar_T']:.1f} °C")

    dew_T = result["dew_T"]
    dew_P = result["dew_P"]
    bub_T = result["bub_T"]
    bub_P = result["bub_P"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dew_T,
        y=dew_P,
        mode="lines+markers",
        name="Dew Point",
        line=dict(color="#2E86AB", width=2),
        marker=dict(size=5),
        hovertemplate="Dew Point<br>T: %{x:.1f} °C<br>P: %{y:.2f} bara<extra></extra>",
    ))
    if len(bub_T) > 0:
        fig.add_trace(go.Scatter(
            x=bub_T,
            y=bub_P,
            mode="lines+markers",
            name="Bubble Point",
            line=dict(color="#E63946", width=2),
            marker=dict(size=5),
            hovertemplate="Bubble Point<br>T: %{x:.1f} °C<br>P: %{y:.2f} bara<extra></extra>",
        ))

    fig.add_trace(go.Scatter(
        x=[result["cricondentherm_T"]],
        y=[result["cricondentherm_P"]],
        mode="markers+text",
        name=f"Cricondentherm ({result['cricondentherm_T']:.1f} °C)",
        marker=dict(color="#F4A261", size=14, symbol="diamond"),
        text=["Cricondentherm"],
        textposition="bottom center",
        hovertemplate=(
            f"Cricondentherm<br>"
            f"T: {result['cricondentherm_T']:.1f} °C<br>"
            f"P: {result['cricondentherm_P']:.2f} bara<extra></extra>"
        ),
    ))

    fig.add_trace(go.Scatter(
        x=[result["cricondenbar_T"]],
        y=[result["cricondenbar_P"]],
        mode="markers+text",
        name=f"Cricondenbar ({result['cricondenbar_P']:.1f} bara)",
        marker=dict(color="#7B2CBF", size=14, symbol="diamond"),
        text=["Cricondenbar"],
        textposition="top center",
        hovertemplate=(
            f"Cricondenbar<br>"
            f"T: {result['cricondenbar_T']:.1f} °C<br>"
            f"P: {result['cricondenbar_P']:.2f} bara<extra></extra>"
        ),
    ))

    if result["critical_T"] is not None:
        fig.add_trace(go.Scatter(
            x=[result["critical_T"]],
            y=[result["critical_P"]],
            mode="markers+text",
            name=f"Critical Point",
            marker=dict(color="#2D6A4F", size=12, symbol="star"),
            text=["Critical"],
            textposition="top right",
            hovertemplate=(
                f"Critical Point<br>"
                f"T: {result['critical_T']:.1f} °C<br>"
                f"P: {result['critical_P']:.2f} bara<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=dict(text=f"Phase Envelope (PT Diagram) — {result['model_name']} EoS", font=dict(size=20)),
        xaxis_title="Temperature (°C)",
        yaxis_title="Pressure (bara)",
        hovermode="closest",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        template="plotly_white",
        height=500,
    )

    st.plotly_chart(fig, width='stretch')
    st.divider()

    col_dew, col_bub = st.columns(2)

    with col_dew:
        st.write("**Dew point curve**")
        st.dataframe(
            pd.DataFrame({
                "Temperature [°C]": [round(t, 2) for t in dew_T],
                "Pressure [bara]":  [round(p, 2) for p in dew_P],
            }),
            hide_index=True,
            width='stretch',
        )

    with col_bub:
        if len(bub_T) > 0:
            st.write("**Bubble point curve**")
            st.dataframe(
                pd.DataFrame({
                    "Temperature [°C]": [round(t, 2) for t in bub_T],
                    "Pressure [bara]":  [round(p, 2) for p in bub_P],
                }),
                hide_index=True,
                width='stretch',
            )
