"""
Single P&T calculation component for the Gas Properties module.
Calculates all gas properties at a single pressure and temperature point.
"""

import pandas as pd
import pvtlib
import streamlit as st

# ── Property catalogue ─────────────────────────────────────────────────────────
PROPERTIES = {
    "rho":    ("Mass Density",              "kg/m³",        "{:.5f}"),
    "w":      ("Speed of Sound",            "m/s",          "{:.3f}"),
    "z":      ("Compressibility Factor",    "–",            "{:.6f}"),
    "cp":     ("Isobaric Heat Capacity",    "J/(mol·K)",    "{:.4f}"),
    "cv":     ("Isochoric Heat Capacity",   "J/(mol·K)",    "{:.4f}"),
    "kappa":  ("Isentropic Exponent",       "–",            "{:.6f}"),
    "h":      ("Enthalpy",                  "J/mol",        "{:.4f}"),
    "s":      ("Entropy",                   "J/(mol·K)",    "{:.6f}"),
    "u":      ("Internal Energy",           "J/mol",        "{:.4f}"),
    "g":      ("Gibbs Energy",              "J/mol",        "{:.4f}"),
    "jt":     ("Joule-Thomson Coefficient", "K/Pa",         "{:.8f}"),
    "mm":     ("Molar Mass",                "g/mol",        "{:.4f}"),
}


def render(composition: dict | None):
    """Render the single P&T calculation UI."""

    st.subheader("Single Point Calculation")
    st.caption("Calculate all gas properties at a single pressure–temperature point using the AGA8 equation of state.")

    if composition is None:
        return

    # ── Inputs ────────────────────────────────────────────────────────────────
    st.markdown("#### Operating Conditions")
    c1, c2 = st.columns(2)
    pressure_unit = c1.selectbox("Pressure unit", ["bara", "barg", "kPa", "MPa"], index=0, key="single_p_unit")
    pressure = c2.number_input(
        f"Pressure [{pressure_unit}]",
        min_value=0.0, max_value=1000.0, value=10.0, step=0.1, format="%.3f",
        key="single_pressure",
    )

    c3, c4 = st.columns(2)
    equation = c3.selectbox(
        "AGA8 equation", ["GERG-2008", "DETAIL"], index=0, key="single_eos",
        help="GERG-2008 is recommended for natural gas mixtures.",
    )
    temperature_unit = c4.selectbox(
        "Temperature unit", ["C", "K"], index=0, key="single_t_unit",
        format_func=lambda x: "°C" if x == "C" else "K",
    )
    temp_label = "°C" if temperature_unit == "C" else "K"
    t_floor = -273.15 if temperature_unit == "C" else 0.0

    c5, c6 = st.columns(2)
    temperature = c5.number_input(
        f"Temperature [{temp_label}]",
        min_value=t_floor, max_value=2000.0, value=20.0, step=0.5, format="%.2f",
        key="single_temperature",
    )

    calculate = st.button("Calculate", type="primary", key="single_calc_btn")

    # ── Calculation ────────────────────────────────────────────────────────────
    if not calculate:
        return

    try:
        aga8 = pvtlib.AGA8(equation)
        result = aga8.calculate_from_PT(
            composition=composition,
            pressure=float(pressure),
            temperature=float(temperature),
            pressure_unit=pressure_unit,
            temperature_unit=temperature_unit,
        )
    except Exception as exc:
        st.error(f"Calculation failed: {exc}")
        return

    # ── Results ────────────────────────────────────────────────────────────────
    st.success(
        f"Results for **{equation}** at "
        f"**{pressure:.3f} {pressure_unit}** / **{temperature:.2f} {temp_label}**"
    )

    key_props = ["rho", "w", "z", "kappa"]
    cols = st.columns(4)
    for col, key in zip(cols, key_props):
        name, unit, fmt = PROPERTIES[key]
        col.metric(label=f"{name} [{unit}]", value=fmt.format(result[key]))

    st.divider()

    rows = [
        {"Property": name, "Symbol": key, "Value": fmt.format(result[key]), "Unit": unit}
        for key, (name, unit, fmt) in PROPERTIES.items()
    ]
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

    # ── CSV download ───────────────────────────────────────────────────────────
    norm_comp = {k: round(v * 100, 6) for k, v in result["gas_composition"].items() if v > 0}
    csv_rows = [{"Property": name, "Symbol": key, "Value": float(fmt.format(result[key])), "Unit": unit}
                for key, (name, unit, fmt) in PROPERTIES.items()]
    comp_rows = [{"Property": f"Composition – {k}", "Symbol": k, "Value": v, "Unit": "mol%"}
                 for k, v in norm_comp.items()]
    csv_df = pd.DataFrame(csv_rows + comp_rows)
    st.download_button(
        label="Download results (CSV)",
        data=csv_df.to_csv(index=False).encode(),
        file_name=f"gas_properties_{equation}_{pressure:.3g}{pressure_unit}_{temperature:.4g}{temp_label}.csv",
        mime="text/csv",
        key="single_dl_csv",
    )

    with st.expander("Normalised composition used in calculation"):
        comp_used = {k: f"{v * 100:.4f} mol%" for k, v in result["gas_composition"].items() if v > 0}
        comp_df = pd.DataFrame.from_dict(comp_used, orient="index", columns=["mol%"])
        comp_df.index.name = "Component"
        st.dataframe(comp_df, width='stretch')
