"""
EoS Comparison tab — DETAIL vs GERG-2008

Calculates the relative deviation (%) in gas properties (ρ, Z, w, κ) between
the DETAIL and GERG-2008 equations of state across a user-defined pressure range
at a fixed temperature.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from ..domain import NEQSIM_NAMES as _NEQSIM_NAMES

_STATE_GRID = "gp_eos_cmp_grid"
_STATE_CCT  = "gp_eos_cmp_cct"

_CCT_EOS_OPTIONS = {
    "SRK (Soave-Redlich-Kwong)": "srk",
    "PR (Peng-Robinson)": "pr",
    "UMR-PRU (recommended for HC dew point)": "pr-umr",
}

COMPARE_PROPS = {
    "rho":   ("Mass Density",              "kg/m³"),
    "z":     ("Compressibility Factor",    "–"),
    "w":     ("Speed of Sound",            "m/s"),
    "kappa": ("Isentropic Exponent",       "–"),
    "cp":    ("Isobaric Heat Capacity",    "J/(mol·K)"),
    "cv":    ("Isochoric Heat Capacity",   "J/(mol·K)"),
    "h":     ("Enthalpy",                  "J/mol"),
    "s":     ("Entropy",                   "J/(mol·K)"),
    "u":     ("Internal Energy",           "J/mol"),
    "g":     ("Gibbs Energy",              "J/mol"),
    "jt":    ("Joule-Thomson Coefficient", "K/Pa"),
    "mm":    ("Molar Mass",                "g/mol"),
}

DEFAULT_COMPARE_PROPS = ["rho", "z", "w", "kappa"]


def _comp_key(composition: dict) -> str:
    """Return a stable hash for a composition."""
    return hashlib.md5(json.dumps(composition, sort_keys=True).encode()).hexdigest()


def _calc_cricondentherm(composition: dict, eos_label: str) -> float:
    """Calculate the cricondentherm temperature for a composition."""
    from neqsim.thermo import TPflash, fluid, phaseenvelope

    model = _CCT_EOS_OPTIONS[eos_label]
    total = sum(composition.values())
    norm = {k: v / total for k, v in composition.items() if v > 0.0}

    gas_fluid = fluid(model)
    for comp, frac in norm.items():
        if comp in _NEQSIM_NAMES:
            gas_fluid.addComponent(_NEQSIM_NAMES[comp], frac)

    gas_fluid.setTemperature(15.0, "C")
    gas_fluid.setPressure(1.0, "bara")
    gas_fluid.setMixingRule(2)
    TPflash(gas_fluid)
    env = phaseenvelope(gas_fluid, False)
    cct = env.get("cricondentherm")
    return float(cct[0]) - 273.15


def _grid_key(composition: dict, p_min: float, p_max: float, n_pts: int,
              temperature: float, p_unit: str, t_unit: str) -> tuple:
    """Build a cache key for a comparison grid."""
    return (_comp_key(composition), p_min, p_max, n_pts, temperature, p_unit, t_unit)


def _run_grid(composition: dict, pressures: list[float], temperature: float,
              p_unit: str, t_unit: str) -> dict:
    """Calculate DETAIL and GERG property grids over the pressure range."""
    import pvtlib

    gerg = pvtlib.AGA8("GERG-2008")
    detail = pvtlib.AGA8("DETAIL")

    results: dict[str, list] = {f"{prop}_{eq}": [] for prop in COMPARE_PROPS for eq in ("gerg", "detail")}

    for p in pressures:
        for eq_name, aga8 in (("gerg", gerg), ("detail", detail)):
            res = aga8.calculate_from_PT(
                composition=composition,
                pressure=p,
                temperature=temperature,
                pressure_unit=p_unit,
                temperature_unit=t_unit,
            )
            for prop in COMPARE_PROPS:
                results[f"{prop}_{eq_name}"].append(res[prop])

    return results


def render(composition: dict | None) -> None:
    """Render the DETAIL vs GERG-2008 comparison tab."""

    st.subheader("EoS Comparison: DETAIL vs GERG-2008")
    st.caption(
        "Compares gas properties calculated by the DETAIL and GERG-2008 equations of state "
        "across a pressure range at a fixed temperature. "
        "Results show the relative deviation (%) of DETAIL relative to GERG-2008: "
        "δ = (DETAIL − GERG-2008) / |GERG-2008| × 100 %."
    )
    st.warning(
        "This comparison does not account for two-phase behavior. Comparing equations inside "
        "the two-phase region will give wrong or non-physical results. Use the cricondentherm "
        "temperature mode to place the comparison temperature above the phase envelope.",
        icon="⚠️",
    )
    with st.expander("Method and temperature handling", expanded=False):
        st.markdown(
            """
The comparison evaluates AGA8 DETAIL and GERG-2008 at the same composition and pressure grid,
using one fixed temperature for the full pressure sweep. The plotted value is the relative
deviation of DETAIL from GERG-2008:

`100 × (DETAIL - GERG-2008) / |GERG-2008| [%]`

**Temperature modes**

- **Manual** — use the temperature entered by the user. This is useful when you know the gas is
  single phase across the selected pressure range.
- **From cricondentherm** — calculate the cricondentherm with NeqSim and set the comparison
  temperature to `cricondentherm + safety margin`. This helps keep the pressure sweep outside
  the two-phase region.

AGA8 DETAIL and GERG-2008 are single-phase gas calculations in this workflow. The app does not
perform a flash calculation or remove points that enter the two-phase region. If the selected
temperature intersects the phase envelope, the comparison is not physically meaningful. For
phase-behavior checks, use the **Phase Envelope** or **Flash Calculation** tabs.
            """
        )

    if composition is None:
        st.info("Enter a valid composition above to enable the EoS comparison.")
        return

    st.markdown("#### Settings")
    col_p, col_t = st.columns(2)

    with col_p:
        p_unit = st.selectbox("Pressure unit", ["bara", "barg", "kPa", "MPa"],
                              index=0, key="ecmp_p_unit")
        c1, c2 = st.columns(2)
        with c1:
            p_min = st.number_input(f"P min [{p_unit}]", min_value=0.01, value=1.0,
                                    step=1.0, format="%.2f", key="ecmp_p_min")
        with c2:
            p_max = st.number_input(f"P max [{p_unit}]", min_value=0.1, value=300.0,
                                    step=10.0, format="%.1f", key="ecmp_p_max")
        n_pts = st.slider("Number of pressure points", min_value=20, max_value=500,
                          value=100, step=10, key="ecmp_n_pts")

    with col_t:
        t_unit = st.selectbox("Temperature unit", ["C", "K"], index=0,
                              key="ecmp_t_unit",
                              format_func=lambda x: "°C" if x == "C" else "K")
        t_label = "°C" if t_unit == "C" else "K"
        t_floor = -273.15 if t_unit == "C" else 0.0

        t_mode = st.radio("Temperature mode",
                          ["Manual", "From cricondentherm"],
                          index=1,
                          horizontal=True, key="ecmp_t_mode")

        if t_mode == "Manual":
            temperature = st.number_input(
                f"Temperature [{t_label}]",
                min_value=t_floor, value=60.0, step=1.0, format="%.1f",
                key="ecmp_t_manual",
            )
        else:
            cct_eos = st.selectbox("EoS for cricondentherm",
                                   list(_CCT_EOS_OPTIONS.keys()), index=0,
                                   key="ecmp_cct_eos")
            t_margin = st.number_input(
                "Safety margin above cricondentherm [°C]",
                min_value=0.0, value=10.0, step=1.0, format="%.1f",
                key="ecmp_cct_margin",
            )

            cct_cache_key = f"ecmp_cct_{_comp_key(composition)}_{cct_eos}"
            if st.button("Calculate cricondentherm", key="ecmp_cct_btn"):
                with st.spinner("Calculating cricondentherm (neqsim)…"):
                    try:
                        cct_val = _calc_cricondentherm(composition, cct_eos)
                        st.session_state[cct_cache_key] = cct_val
                    except Exception as exc:
                        st.error(f"Cricondentherm calculation failed: {exc}")

            cct_val = st.session_state.get(cct_cache_key)
            if cct_val is not None:
                st.info(f"Cricondentherm: **{cct_val:.1f} °C**  →  temperature set to **{cct_val + t_margin:.1f} °C**")
                temperature = cct_val + t_margin if t_unit == "C" else cct_val + t_margin + 273.15
            else:
                st.caption("Click **Calculate cricondentherm** to auto-set temperature.")
                temperature = 60.0

    if t_mode == "Manual":
        for eos_label in _CCT_EOS_OPTIONS:
            cct_cache_key = f"ecmp_cct_{_comp_key(composition)}_{eos_label}"
            cached_cct = st.session_state.get(cct_cache_key)
            t_in_celsius = temperature if t_unit == "C" else temperature - 273.15
            if cached_cct is not None and t_in_celsius <= cached_cct:
                st.warning(
                    f"The selected temperature ({t_in_celsius:.1f} °C) is at or below the "
                    f"cricondentherm ({cached_cct:.1f} °C, {eos_label}). "
                    "At this temperature the gas may enter the two-phase region at high pressures, "
                    "which will cause errors or non-physical results in the comparison.",
                    icon="⚠️",
                )
                break

    if p_min >= p_max:
        st.error("P min must be less than P max.")
        return

    prop_labels = {k: f"{v[0]} [{v[1]}]" for k, v in COMPARE_PROPS.items()}
    selected_props = st.multiselect(
        "Properties to compare",
        options=list(COMPARE_PROPS.keys()),
        default=DEFAULT_COMPARE_PROPS,
        format_func=lambda k: prop_labels[k],
        key="ecmp_props",
    )
    if not selected_props:
        st.warning("Select at least one property.")
        return

    grid_key = _grid_key(composition, p_min, p_max, n_pts, temperature, p_unit, t_unit)
    cached = st.session_state.get(_STATE_GRID)
    has_cache = cached is not None and cached.get("key") == grid_key

    btn_label = "▶ Run comparison" if not has_cache else "🔄 Re-run comparison"
    col_btn, col_info = st.columns([2, 5])
    with col_btn:
        run_clicked = st.button(btn_label, type="primary", key="ecmp_run_btn")
    if has_cache:
        with col_info:
            t_display = f"{temperature:.1f} {t_label}"
            st.caption(
                f"✅ Results shown for T = {t_display}, "
                f"P = {p_min}–{p_max} {p_unit} ({n_pts} points). "
                "Change settings and re-run to update."
            )

    if run_clicked:
        # If "From cricondentherm" mode is selected and cricondentherm hasn't been calculated yet, calculate it first
        if t_mode == "From cricondentherm":
            cct_eos = st.session_state.get("ecmp_cct_eos") or list(_CCT_EOS_OPTIONS.keys())[0]
            t_margin = st.session_state.get("ecmp_cct_margin", 10.0)
            cct_cache_key = f"ecmp_cct_{_comp_key(composition)}_{cct_eos}"
            cct_val = st.session_state.get(cct_cache_key)
            
            if cct_val is None:
                with st.spinner("Calculating cricondentherm (neqsim)…"):
                    try:
                        cct_val = _calc_cricondentherm(composition, cct_eos)
                        st.session_state[cct_cache_key] = cct_val
                    except Exception as exc:
                        st.error(f"Cricondentherm calculation failed: {exc}")
                        return
            
            # Use cricondentherm to set temperature
            temperature = cct_val + t_margin if t_unit == "C" else cct_val + t_margin + 273.15
        
        pressures = list(np.linspace(p_min, p_max, n_pts))
        with st.spinner("Calculating GERG-2008 and DETAIL properties…"):
            try:
                grid_data = _run_grid(composition, pressures, temperature, p_unit, t_unit)
                st.session_state[_STATE_GRID] = {
                    "key": grid_key,
                    "pressures": pressures,
                    "data": grid_data,
                    "temperature": temperature,
                    "t_unit": t_unit,
                    "p_unit": p_unit,
                }
            except Exception as exc:
                st.error(f"Comparison calculation failed: {exc}")
                return

    state = st.session_state.get(_STATE_GRID)
    if state is None or state.get("key") != grid_key:
        return

    pressures = state["pressures"]
    data = state["data"]
    t_display = (
        f"{state['temperature']:.1f} {'°C' if state['t_unit'] == 'C' else 'K'}"
    )

    st.divider()
    st.markdown(f"#### Relative deviation: DETAIL vs GERG-2008 — T = {t_display}")
    st.caption(
        "Positive values mean DETAIL calculates a higher value than GERG-2008; "
        "negative values mean DETAIL calculates a lower value."
    )

    plot_mode = st.radio(
        "Plot mode",
        ["All in one plot", "Individual plots"],
        index=0,
        horizontal=True,
        key="ecmp_plot_mode",
    )

    _COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
        "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
        "#bcbd22", "#17becf", "#aec7e8", "#ffbb78",
    ]

    prop_devs: dict[str, np.ndarray] = {}
    for prop in selected_props:
        gerg_vals = np.array(data[f"{prop}_gerg"])
        detail_vals = np.array(data[f"{prop}_detail"])
        with np.errstate(invalid="ignore", divide="ignore"):
            prop_devs[prop] = np.where(
                gerg_vals != 0,
                (detail_vals - gerg_vals) / np.abs(gerg_vals) * 100.0,
                np.nan,
            )

    if plot_mode == "All in one plot":
        fig = go.Figure()
        for i, prop in enumerate(selected_props):
            prop_name, prop_unit = COMPARE_PROPS[prop]
            rel_dev = prop_devs[prop]
            color = _COLORS[i % len(_COLORS)]
            fig.add_trace(go.Scatter(
                x=pressures,
                y=rel_dev,
                mode="lines",
                name=f"{prop_name} [{prop_unit}]",
                line=dict(color=color, width=2),
                hovertemplate=(
                    f"<b>{prop_name}</b><br>"
                    f"P: %{{x:.2f}} {state['p_unit']}<br>"
                    f"δ: %{{y:.4f}} %<extra></extra>"
                ),
            ))
        fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
        fig.update_layout(
            xaxis_title=f"Pressure [{state['p_unit']}]",
            yaxis_title="Relative deviation (%)",
            height=480,
            margin=dict(l=60, r=200, t=30, b=60),
            template="plotly_white",
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        for i, prop in enumerate(selected_props):
            prop_name, prop_unit = COMPARE_PROPS[prop]
            rel_dev = prop_devs[prop]
            max_abs = np.nanmax(np.abs(rel_dev))
            color = _COLORS[i % len(_COLORS)]

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=pressures,
                y=rel_dev,
                mode="lines",
                line=dict(color=color, width=2),
                name=f"{prop_name}",
                hovertemplate=(
                    f"P: %{{x:.2f}} {state['p_unit']}<br>"
                    f"δ: %{{y:.4f}} %<extra></extra>"
                ),
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
            fig.update_layout(
                title=dict(text=f"{prop_name} [{prop_unit}]", font=dict(size=16)),
                xaxis_title=f"Pressure [{state['p_unit']}]",
                yaxis_title="Relative deviation (%)",
                height=340,
                margin=dict(l=60, r=20, t=50, b=60),
                template="plotly_white",
                showlegend=False,
                annotations=[dict(
                    text=f"Max |δ| = {max_abs:.4f} %",
                    xref="paper", yref="paper",
                    x=0.99, y=0.97,
                    xanchor="right", yanchor="top",
                    showarrow=False,
                    font=dict(size=12, color="gray"),
                    bgcolor="rgba(255,255,255,0.7)",
                )],
            )
            st.plotly_chart(fig, use_container_width=True)
