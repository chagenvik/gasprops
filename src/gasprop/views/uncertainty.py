"""
Uncertainty Analysis tab for the Gas Properties module.

Propagates compositional and P/T uncertainties to AGA8-derived gas properties
using uncertaintylib:
  - Standard uncertainty (GUM-style sensitivity-coefficient method)
  - Monte Carlo simulation

Supports three built-in compositional uncertainty models (ASTM D1945,
NORSOK I-106, Hagenvik et al. 2024) as well as fully manual entry.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import pvtlib
import streamlit as st
from uncertaintylib import uncertainty_functions as uf
from uncertaintylib.uncertainty_models import gas_composition as gc_models

PROPERTIES = {
    "rho":   ("Mass Density",              "kg/m³",        "{:.5f}"),
    "z":     ("Compressibility Factor",    "–",            "{:.6f}"),
    "w":     ("Speed of Sound",            "m/s",          "{:.3f}"),
    "cp":    ("Isobaric Heat Capacity",    "J/(mol·K)",    "{:.4f}"),
    "cv":    ("Isochoric Heat Capacity",   "J/(mol·K)",    "{:.4f}"),
    "kappa": ("Isentropic Exponent",       "–",            "{:.6f}"),
    "h":     ("Enthalpy",                  "J/mol",        "{:.4f}"),
    "s":     ("Entropy",                   "J/(mol·K)",    "{:.6f}"),
    "u":     ("Internal Energy",           "J/mol",        "{:.4f}"),
    "g":     ("Gibbs Energy",              "J/mol",        "{:.4f}"),
    "jt":    ("Joule-Thomson Coefficient", "K/Pa",         "{:.8f}"),
    "mm":    ("Molar Mass",                "g/mol",        "{:.4f}"),
}

DEFAULT_PROPERTIES = ["rho", "z", "w", "kappa", "mm"]
MAX_MONTE_CARLO_RUNS = 100_000

COMP_MODELS = {
    "Manual": None,
    "ASTM D1945": gc_models.component_uncertainty_from_ASTM_D1945,
    "NORSOK I-106": gc_models.component_uncertainty_from_norsok_I106,
    "Hagenvik et al. (2024)": gc_models.component_uncertainty_from_haagenvik2024,
}

_MODEL_ALLOWED: dict[str, set[str] | None] = {
    "Manual": None,
    "ASTM D1945": {"N2", "CO2", "C1", "C2", "C3", "iC4", "nC4", "iC5", "nC5", "nC6", "nC7", "nC8", "nC9", "nC10"},
    "NORSOK I-106": None,
    "Hagenvik et al. (2024)": {"N2", "CO2", "C1", "C2", "C3", "iC4", "nC4", "iC5", "nC5", "nC6", "nC7", "nC8", "nC9", "nC10"},
}


def _filter_composition(composition: dict, model_name: str) -> tuple[dict, list[str]]:
    """Filter out unsupported components for the selected uncertainty model."""
    allowed = _MODEL_ALLOWED.get(model_name)
    if allowed is None:
        return dict(composition), []

    removed = [k for k in composition if k not in allowed]
    filtered = {k: v for k, v in composition.items() if k in allowed}

    if filtered:
        total = sum(filtered.values())
        if total > 0:
            filtered = {k: v / total * 100.0 for k, v in filtered.items()}

    return filtered, removed


_STATE_STD = "gp_unc_std_result"
_STATE_MC  = "gp_unc_mc_result"
_STATE_INPUT = "gp_unc_input_snapshot"


def _make_calc_function(equation: str, p_unit: str, t_unit: str, comp_keys: list[str]):
    """Create an AGA8 calculation function for uncertainty propagation."""
    def _calc(input_dict: dict) -> dict:
        """Run one AGA8 property calculation for the supplied inputs."""
        composition = {k: input_dict[k] for k in comp_keys if k in input_dict}
        pressure = input_dict["pressure"]
        temperature = input_dict["temperature"]
        aga8 = pvtlib.AGA8(equation)
        result = aga8.calculate_from_PT(
            composition=composition,
            pressure=pressure,
            temperature=temperature,
            pressure_unit=p_unit,
            temperature_unit=t_unit,
        )
        return {k: result[k] for k in PROPERTIES}
    return _calc


def uncertainty_input_from_model(
    composition: dict,
    model_name: str,
    p_mean: float,
    t_mean: float,
    p_abs: float,
    p_rel: float,
    t_abs: float,
    t_rel: float,
) -> dict:
    """Build an uncertainty input payload from a built-in composition model."""
    model_fn = COMP_MODELS[model_name]
    model_result = model_fn(composition)

    mean = {**model_result["mean"], "pressure": p_mean, "temperature": t_mean}
    std_unc = {**model_result["standard_uncertainty"], "pressure": p_abs, "temperature": t_abs}
    std_unc_pct = {k: 0.0 for k in mean}
    std_unc_pct["pressure"] = p_rel
    std_unc_pct["temperature"] = t_rel
    distribution = {**model_result["distribution"], "pressure": "normal", "temperature": "normal"}

    return {
        "mean": mean,
        "standard_uncertainty": std_unc,
        "standard_uncertainty_percent": std_unc_pct,
        "distribution": distribution,
    }


def build_uncertainty_input(
    composition: dict,
    unc_df: pd.DataFrame,
    p_mean: float,
    t_mean: float,
    p_abs: float,
    p_rel: float,
    t_abs: float,
    t_rel: float,
) -> dict:
    """Build an uncertainty input payload from a manual uncertainty table."""
    mean: dict = {}
    std_unc: dict = {}
    std_unc_pct: dict = {}
    distribution: dict = {}

    for _, row in unc_df.iterrows():
        comp = row["Component"]
        mean[comp] = float(row["mol% (mean)"])
        abs_val = float(row["Abs. std unc. (mol%)"] or 0.0)
        rel_val = float(row["Rel. std unc. (%)"] or 0.0)
        std_unc[comp] = abs_val
        std_unc_pct[comp] = rel_val
        distribution[comp] = "normal"

    mean["pressure"] = p_mean
    mean["temperature"] = t_mean
    std_unc["pressure"] = p_abs
    std_unc["temperature"] = t_abs
    std_unc_pct["pressure"] = p_rel
    std_unc_pct["temperature"] = t_rel
    distribution["pressure"] = "normal"
    distribution["temperature"] = "normal"

    return {
        "mean": mean,
        "standard_uncertainty": std_unc,
        "standard_uncertainty_percent": std_unc_pct,
        "distribution": distribution,
    }


def _render_standard_results(std_result: dict, selected_props: list[str]) -> None:
    """Render standard-uncertainty results and contribution plots."""
    st.markdown("#### Standard Uncertainty Results")

    rows = []
    for prop in selected_props:
        name, unit, _ = PROPERTIES[prop]
        rows.append({
            "Property": f"{name} [{unit}]",
            "Value": f"{std_result['value'][prop]:.6g}",
            "u (k=1)": f"{std_result['u'][prop]:.2g}",
            "U (k=2)": f"{std_result['U'][prop]:.2g}",
            "U% (k=2)": f"{std_result['U_perc'][prop]:.2g} %",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("#### Uncertainty Contributions")
    st.caption(
        "Each bar shows what percentage of the combined variance in that property "
        "is contributed by each input (composition component, pressure, temperature). "
        "Bars sum to 100 %."
    )

    for prop in selected_props:
        name, unit, _ = PROPERTIES[prop]
        contributions = std_result["contribution"].get(prop, {})
        if not contributions:
            continue
        sorted_items = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
        labels = [k for k, _ in sorted_items]
        values = [v for _, v in sorted_items]

        colors = [
            "#d62728" if k in ("pressure", "temperature") else "#1f77b4"
            for k in labels
        ]

        fig = go.Figure(go.Bar(
            x=labels,
            y=values,
            marker_color=colors,
            text=[f"{v:.1f}%" for v in values],
            textposition="outside",
        ))
        fig.update_layout(
            title=f"{name} [{unit}] — contribution (%)",
            yaxis=dict(title="Contribution (%)", range=[0, max(values) * 1.15]),
            xaxis=dict(title="Input"),
            height=380,
            margin=dict(l=50, r=20, t=50, b=80),
        )
        st.plotly_chart(fig, use_container_width=True)


def _render_mc_results(mc_df: pd.DataFrame, mc_stats: pd.DataFrame, selected_props: list[str]) -> None:
    """Render Monte Carlo summary tables and distributions."""
    st.markdown("#### Monte Carlo Results")

    rows = []
    for prop in selected_props:
        if prop not in mc_stats.index:
            continue
        name, unit, _ = PROPERTIES[prop]
        s = mc_stats.loc[prop]
        rows.append({
            "Property": f"{name} [{unit}]",
            "Mean": f"{s['mean']:.6g}",
            "Std dev (u)": f"{s['std_dev']:.2g}",
            "U (k=2)": f"{s['std_dev_k2']:.2g}",
            "U% (k=2)": f"{s['std_dev_percent_k2']:.2g} %" if not math.isnan(float(s['std_dev_percent_k2'])) else "–",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("#### Monte Carlo Distributions")
    histogram_bins = st.slider(
        "Histogram bins",
        min_value=10,
        max_value=200,
        value=100,
        step=5,
        key="unc_mc_hist_bins",
        help="Adjust the number of bins used in Monte Carlo distribution histograms.",
    )
    for prop in selected_props:
        if prop not in mc_df.columns:
            continue
        name, unit, _ = PROPERTIES[prop]
        vals = mc_df[prop].dropna()
        if vals.empty:
            continue
        mean_v = vals.mean()
        std_v = vals.std()

        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=vals,
            nbinsx=histogram_bins,
            name="MC samples",
            marker_color="#1f77b4",
            opacity=0.75,
        ))
        for sigma, label, color in [
            (mean_v, "Mean", "#2ca02c"),
            (mean_v - 2 * std_v, "Mean − 2σ", "#d62728"),
            (mean_v + 2 * std_v, "Mean + 2σ", "#d62728"),
        ]:
            fig.add_vline(x=sigma, line_dash="dash", line_color=color,
                          annotation_text=label, annotation_position="top")
        fig.update_layout(
            title=f"{name} [{unit}] — MC distribution (n={len(vals):,})",
            xaxis_title=f"{name} [{unit}]",
            yaxis_title="Count",
            height=380,
            margin=dict(l=50, r=20, t=50, b=60),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)


def render(composition: dict | None) -> None:
    """Render the uncertainty analysis tab."""
    st.subheader("Uncertainty Analysis")
    st.caption(
        "Propagate compositional and P/T measurement uncertainties to AGA8 gas properties "
        "using the GUM sensitivity-coefficient method and Monte Carlo simulation. "
        "Only input uncertainties are included; model uncertainties in GERG-2008 and DETAIL are not."
    )
    st.info(
        "**⚠️ All uncertainty inputs must be entered as one standard deviation (1σ, k=1).** "
        "The expanded uncertainty at coverage factor k=2 (≈ 95 % confidence) is reported in the results. "
        "These results reflect input uncertainty only, not model-form uncertainty.",
        icon="ℹ️",
    )
    st.markdown(
        "**If both absolute and relative standard uncertainties are provided**, "
        "the library converts the relative value to an absolute value (= mean × rel% / 100) "
        "and uses whichever of the two is **larger**. "
        "You can therefore leave the one you don't use at zero.\n\n"
        "**Monte Carlo simulation** draws samples from a **normal distribution** for each input "
        "(composition components, pressure, temperature) using the specified mean and standard deviation.\n\n"
        "> **Note:** The uncertainty calculation only accounts for input uncertainties (pressure, temperature "
        "and composition). Model uncertainties inherent to GERG-2008 and DETAIL are **not** included. "
        "As a result, the uncertainty results for GERG-2008 and DETAIL will be nearly identical for the same inputs."
    )

    if composition is None:
        st.info("Enter a gas composition in the composition table above to enable uncertainty analysis.")
        return

    st.markdown("#### Operating Conditions")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        equation = st.selectbox("AGA8 equation", ["GERG-2008", "DETAIL"], index=0, key="unc_eos")
    with c2:
        p_unit = st.selectbox("Pressure unit", ["bara", "barg", "kPa", "MPa"], index=0, key="unc_p_unit")
    with c3:
        t_unit = st.selectbox("Temperature unit", ["C", "K"], index=0, key="unc_t_unit",
                              format_func=lambda x: "°C" if x == "C" else "K")

    t_label = "°C" if t_unit == "C" else "K"
    t_floor = -273.15 if t_unit == "C" else 0.0

    col_p, col_t = st.columns(2)
    with col_p:
        p_mean = st.number_input(f"Pressure [{p_unit}]", min_value=0.0, value=100.0, step=0.1,
                                 format="%.3f", key="unc_p_mean")
        p_abs = st.number_input(f"Abs. std uncertainty [{p_unit}]", min_value=0.0, value=0.0,
                                step=0.001, format="%.4f", key="unc_p_abs",
                                help="Standard uncertainty (1σ) in pressure, absolute.")
        p_rel = st.number_input("Rel. std uncertainty pressure [%]", min_value=0.0, value=0.15,
                                step=0.01, format="%.3f", key="unc_p_rel",
                                help="Standard uncertainty (1σ) in pressure, as % of value.")
    with col_t:
        temperature = st.number_input(f"Temperature [{t_label}]", min_value=t_floor, value=60.0,
                                      step=0.5, format="%.2f", key="unc_t_mean")
        t_abs = st.number_input(f"Abs. std uncertainty [{t_label}]", min_value=0.0, value=0.15,
                                step=0.001, format="%.4f", key="unc_t_abs",
                                help="Standard uncertainty (1σ) in temperature, absolute.")
        t_rel = st.number_input("Rel. std uncertainty temperature [%]", min_value=0.0, value=0.0,
                                step=0.01, format="%.3f", key="unc_t_rel",
                                help="Standard uncertainty (1σ) in temperature, as % of value.")

    st.markdown("#### Properties to Analyse")
    prop_options = list(PROPERTIES.keys())
    prop_labels = {k: f"{v[0]} [{v[1]}]" for k, v in PROPERTIES.items()}
    selected_props = st.multiselect(
        "Properties",
        options=prop_options,
        default=DEFAULT_PROPERTIES,
        format_func=lambda k: prop_labels[k],
        key="unc_props",
    )
    if not selected_props:
        st.warning("Select at least one property.")
        return

    st.markdown("#### Compositional Uncertainty")
    model_name = st.radio(
        "Uncertainty model",
        options=list(COMP_MODELS.keys()),
        index=list(COMP_MODELS.keys()).index("Hagenvik et al. (2024)"),
        horizontal=True,
        key="unc_model",
    )

    _MODEL_DESCRIPTIONS = {
        "Manual": (
            "Enter the standard uncertainty (1σ) for each component manually. "
            "You can specify an absolute value (mol%), a relative value (%), or both."
        ),
        "ASTM D1945": (
            "Compositional uncertainties based on the **reproducibility** limits in "
            "**ASTM D1945** (§10.1.2), interpreted via the NFOGM GasMet tool. "
            "Expanded uncertainty (k=2) is assigned by concentration band: "
            "< 0.1 mol% → 0.02 mol%, 0.1–1 mol% → 0.07 mol%, 1–5 mol% → 0.10 mol%, "
            "5–10 mol% → 0.12 mol%, > 10 mol% → 0.15 mol%. "
            "Supported components: N₂, CO₂, C1–C10."
        ),
        "NORSOK I-106": (
            "Compositional uncertainties according to **NORSOK I-106:2014** (Table 4). "
            "Expanded uncertainty (k=2) is calculated as a factor × (M_avg / M_i), "
            "where the factor depends on the component's mass fraction "
            "(< 20 mass% → 0.15, 20–50 mass% → 0.30, > 50 mass% → 0.60). "
            "⚠️ This method does **not** account for increased uncertainty in heavier components "
            "and may underestimate uncertainties for rich gas compositions. "
            "Supported components: all GERG-2008 components."
        ),
        "Hagenvik et al. (2024)": (
            "Component uncertainties estimated from **empirical power-law regressions** "
            "fitted to K-lab parallel GC test data (Hagenvik et al., 2024). "
            "Each component has its own fitted coefficients (u = a × xᵇ). "
            "Methane (C1) is intentionally assigned zero uncertainty — after normalisation "
            "to 100 mol%, C1 is fully constrained by the other components. "
            "⚠️ Should only be used for compositions with **≥ 60 mol% methane**. "
            "Supported components: N₂, CO₂, C1–C10. "
            "📄 [Hagenvik et al. (2024) — NFOGM paper](https://nfogm.no/wp-content/uploads/2025/08/1-Single-Phase-1-Exploring-the-Relationship-between-Speed-of-Sound-Density-and-Isentropic-Exponent-Christian-Hagenvik_Equinor.pdf)"
        ),
    }

    with st.expander(f"ℹ️ About: {model_name}", expanded=False):
        st.markdown(_MODEL_DESCRIPTIONS[model_name])

    active_components = {k: v for k, v in composition.items() if v > 0}
    filtered_components, removed_comps = _filter_composition(active_components, model_name)
    if removed_comps:
        st.warning(
            f"The following component(s) are not supported by the **{model_name}** model and have been "
            f"removed before calculation: **{', '.join(removed_comps)}**. "
            "The remaining composition has been re-normalised to 100 mol%.",
            icon="⚠️",
        )

    calc_components = filtered_components if model_name != "Manual" else active_components
    comp_keys = list(calc_components.keys())

    if model_name == "Manual":
        ss_key = "unc_manual_df"
        stored = st.session_state.get(ss_key)
        if stored is not None and list(stored["Component"]) == comp_keys:
            default_df = stored
        else:
            default_df = pd.DataFrame({
                "Component": comp_keys,
                "mol% (mean)": [round(active_components[k], 6) for k in comp_keys],
                "Abs. std unc. (mol%)": [0.0] * len(comp_keys),
                "Rel. std unc. (%)": [0.0] * len(comp_keys),
            })

        st.caption(
            "Enter the standard uncertainty (1σ) for each component. "
            "You can specify absolute (mol%), relative (%), or both — "
            "uncertaintylib will use the larger of the two."
        )
        edited_df = st.data_editor(
            default_df,
            use_container_width=True,
            hide_index=True,
            disabled=["Component", "mol% (mean)"],
            column_config={
                "Component": st.column_config.TextColumn("Component", width="small"),
                "mol% (mean)": st.column_config.NumberColumn("mol% (mean)", format="%.6f"),
                "Abs. std unc. (mol%)": st.column_config.NumberColumn("Abs. std unc. (mol%)", min_value=0.0, format="%.4f"),
                "Rel. std unc. (%)": st.column_config.NumberColumn("Rel. std unc. (%)", min_value=0.0, format="%.4f"),
            },
            key="unc_manual_editor",
        )
        st.session_state[ss_key] = edited_df
        unc_df = edited_df
    else:
        model_fn = COMP_MODELS[model_name]
        try:
            model_result = model_fn(calc_components)
        except Exception as exc:
            st.error(f"Could not compute {model_name} uncertainties: {exc}")
            return
        preview_rows = []
        for comp in comp_keys:
            std_u = model_result["standard_uncertainty"].get(comp, 0.0)
            mean_v = model_result["mean"].get(comp, calc_components[comp])
            rel_u = (std_u / abs(mean_v) * 100) if mean_v != 0 else 0.0
            preview_rows.append({
                "Component": comp,
                "mol% (mean)": round(mean_v, 6),
                "Abs. std unc. (mol%)": round(std_u, 6),
                "Rel. std unc. (%)": round(rel_u, 4),
            })
        preview_df = pd.DataFrame(preview_rows)
        st.caption(f"Compositional uncertainties from **{model_name}** (read-only). Set P/T uncertainties above.")
        st.dataframe(preview_df, use_container_width=True, hide_index=True)
        unc_df = preview_df

    st.markdown("#### Run Analysis")
    col_std, col_mc, col_mc_n = st.columns([2, 2, 1])
    with col_std:
        run_std = st.button("▶ Run standard uncertainty (GUM)", type="primary", key="unc_run_std")
    with col_mc_n:
        if st.session_state.get("unc_mc_n", 10_000) > MAX_MONTE_CARLO_RUNS:
            st.session_state["unc_mc_n"] = MAX_MONTE_CARLO_RUNS
        mc_n = st.number_input("MC samples", min_value=100, max_value=MAX_MONTE_CARLO_RUNS,
                               value=10_000, step=1, key="unc_mc_n")
    with col_mc:
        run_mc = st.button(f"▶ Run Monte Carlo (n = {mc_n:,})", key="unc_run_mc")

    calc_fn = _make_calc_function(equation, p_unit, t_unit, comp_keys)

    if run_std or run_mc:
        try:
            if model_name == "Manual":
                unc_input = build_uncertainty_input(
                    active_components, unc_df,
                    float(p_mean), float(temperature),
                    float(p_abs), float(p_rel),
                    float(t_abs), float(t_rel),
                )
            else:
                unc_input = uncertainty_input_from_model(
                    calc_components, model_name,
                    float(p_mean), float(temperature),
                    float(p_abs), float(p_rel),
                    float(t_abs), float(t_rel),
                )
        except Exception as exc:
            st.error(f"Could not build uncertainty input: {exc}")
            return

        if run_std:
            with st.spinner("Running standard uncertainty analysis…"):
                try:
                    std_result = uf.calculate_uncertainty(unc_input, calc_fn)
                    st.session_state[_STATE_STD] = {
                        "result": std_result,
                        "selected_props": selected_props,
                    }
                except Exception as exc:
                    st.error(f"Standard uncertainty calculation failed: {exc}")

        if run_mc:
            mc_n = min(int(mc_n), MAX_MONTE_CARLO_RUNS)
            with st.spinner(f"Running Monte Carlo simulation (n = {mc_n:,})…"):
                try:
                    mc_df = uf.monte_carlo_simulation(unc_input, calc_fn, n=int(mc_n))
                    mc_stats = uf.calculate_monte_carlo_statistics(mc_df)
                    st.session_state[_STATE_MC] = {
                        "mc_df": mc_df,
                        "mc_stats": mc_stats,
                        "selected_props": selected_props,
                        "n": int(mc_n),
                    }
                except Exception as exc:
                    st.error(f"Monte Carlo simulation failed: {exc}")

    std_state = st.session_state.get(_STATE_STD)
    mc_state = st.session_state.get(_STATE_MC)

    if std_state is None and mc_state is None:
        return

    st.divider()
    res_tabs = []
    if std_state is not None:
        res_tabs.append("Standard Uncertainty")
    if mc_state is not None:
        res_tabs.append("Monte Carlo")

    if len(res_tabs) == 1:
        if std_state is not None:
            _render_standard_results(std_state["result"], selected_props)
        else:
            mc_df = mc_state["mc_df"]
            mc_stats = mc_state["mc_stats"]
            _render_mc_results(mc_df, mc_stats, selected_props)
    else:
        rt1, rt2 = st.tabs(res_tabs)
        with rt1:
            _render_standard_results(std_state["result"], selected_props)
        with rt2:
            mc_df = mc_state["mc_df"]
            mc_stats = mc_state["mc_stats"]
            _render_mc_results(mc_df, mc_stats, selected_props)
