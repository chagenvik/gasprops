"""
3D Surface Plot component for the Gas Properties module.

Generates an interactive Plotly surface of a single gas property over a
user-defined pressure–temperature grid.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pvtlib
import streamlit as st

PROPERTIES = {
    "rho":   ("Mass Density",              "kg/m³"),
    "w":     ("Speed of Sound",            "m/s"),
    "z":     ("Compressibility Factor",    "–"),
    "cp":    ("Isobaric Heat Capacity",    "J/(mol·K)"),
    "cv":    ("Isochoric Heat Capacity",   "J/(mol·K)"),
    "kappa": ("Isentropic Exponent",       "–"),
    "h":     ("Enthalpy",                  "J/mol"),
    "s":     ("Entropy",                   "J/(mol·K)"),
    "u":     ("Internal Energy",           "J/mol"),
    "g":     ("Gibbs Energy",              "J/mol"),
    "jt":    ("Joule-Thomson Coefficient", "K/Pa"),
    "mm":    ("Molar Mass",                "g/mol"),
}


def _calculate_grid(
    composition: dict,
    pressures: np.ndarray,
    temperatures: np.ndarray,
    prop_key: str,
    equation: str,
    pressure_unit: str,
    temperature_unit: str,
) -> np.ndarray:
    aga8 = pvtlib.AGA8(equation)
    z = np.empty((len(temperatures), len(pressures)))
    for i, T in enumerate(temperatures):
        for j, P in enumerate(pressures):
            result = aga8.calculate_from_PT(
                composition=composition,
                pressure=float(P),
                temperature=float(T),
                pressure_unit=pressure_unit,
                temperature_unit=temperature_unit,
            )
            z[i, j] = result[prop_key]
    return z


def render(composition: dict | None) -> None:
    st.subheader("3D Surface Plot")
    st.caption(
        "Interactive surface of a single gas property over a pressure–temperature grid."
    )

    if composition is None:
        return

    c_eq, c_prop = st.columns(2)
    equation = c_eq.selectbox("AGA8 equation", ["GERG-2008", "DETAIL"], index=0, key="surf_eos")
    prop_key = c_prop.selectbox(
        "Property",
        options=list(PROPERTIES.keys()),
        index=0,
        format_func=lambda k: f"{PROPERTIES[k][0]}  [{PROPERTIES[k][1]}]",
        key="surf_prop",
    )

    st.markdown("**Pressure Range**")
    pu_col, _ = st.columns([1, 2])
    pressure_unit = pu_col.selectbox("Pressure unit", ["bara", "barg", "kPa", "MPa"], index=0, key="surf_p_unit")
    cp1, cp2, cp3 = st.columns(3)
    p_min  = cp1.number_input("Min",  value=1.0,   min_value=0.0,  step=5.0,  format="%.2f", key="surf_p_min")
    p_max  = cp2.number_input("Max",  value=200.0, min_value=0.0,  step=5.0,  format="%.2f", key="surf_p_max")
    p_step = cp3.number_input("Step", value=5.0,   min_value=0.01, step=1.0,  format="%.2f", key="surf_p_step")

    st.markdown("**Temperature Range**")
    tu_col, _ = st.columns([1, 2])
    temperature_unit = tu_col.selectbox(
        "Temperature unit", ["C", "K"], index=0, key="surf_t_unit",
        format_func=lambda x: "°C" if x == "C" else "K",
    )
    temp_label = "°C" if temperature_unit == "C" else "K"
    t_default_min = 0.0   if temperature_unit == "C" else 273.15
    t_default_max = 100.0 if temperature_unit == "C" else 373.15
    ct1, ct2, ct3 = st.columns(3)
    t_min  = ct1.number_input(f"Min [{temp_label}]",  value=t_default_min, step=5.0, format="%.1f", key="surf_t_min")
    t_max  = ct2.number_input(f"Max [{temp_label}]",  value=t_default_max, step=5.0, format="%.1f", key="surf_t_max")
    t_step = ct3.number_input(f"Step [{temp_label}]", value=5.0, min_value=0.1, step=1.0, format="%.1f", key="surf_t_step")

    generate = st.button("Generate Surface", type="primary", key="surf_gen_btn")

    if generate:
        if p_min >= p_max:
            st.error("Pressure min must be less than max.")
            st.stop()
        if t_min >= t_max:
            st.error("Temperature min must be less than max.")
            st.stop()

        pressures    = np.arange(p_min, p_max + p_step * 0.5, p_step)
        temperatures = np.arange(t_min, t_max + t_step * 0.5, t_step)

        if len(pressures) * len(temperatures) > 2000:
            st.error(f"Grid too large ({len(pressures) * len(temperatures)} points). Reduce the range or increase the step size.")
            st.stop()

        with st.spinner("Calculating…"):
            try:
                z = _calculate_grid(
                    composition, pressures, temperatures,
                    prop_key, equation, pressure_unit, temperature_unit,
                )
            except Exception as exc:
                st.error(f"Calculation error: {exc}")
                st.stop()

        st.session_state["surf_cache"] = {
            "z_grids":        {prop_key: z},
            "pressures":      pressures,
            "temperatures":   temperatures,
            "equation":       equation,
            "pressure_unit":  pressure_unit,
            "temperature_unit": temperature_unit,
            "temp_label":     temp_label,
            "prop_key":       prop_key,
            "composition":    composition,
        }

    cache = st.session_state.get("surf_cache")
    if cache is None:
        return

    prop_name, prop_unit = PROPERTIES[cache["prop_key"]]

    st.markdown("**Color map**")
    COLORSCALES = [
        "Viridis", "Plasma", "Inferno", "Magma", "Cividis",
        "Turbo", "RdBu", "Portland", "Jet", "Hot", "Greys",
    ]
    cc1, cc2 = st.columns(2)
    color_prop_key = cc1.selectbox(
        "Color variable",
        options=list(PROPERTIES.keys()),
        index=list(PROPERTIES.keys()).index("z"),
        format_func=lambda k: f"{PROPERTIES[k][0]}  [{PROPERTIES[k][1]}]",
        key="surf_color_prop",
    )
    colorscale = cc2.selectbox("Color palette", options=COLORSCALES, index=0, key="surf_colorscale")

    if color_prop_key not in cache["z_grids"]:
        with st.spinner(f"Calculating {PROPERTIES[color_prop_key][0]} for color…"):
            try:
                cache["z_grids"][color_prop_key] = _calculate_grid(
                    cache["composition"], cache["pressures"], cache["temperatures"],
                    color_prop_key, cache["equation"],
                    cache["pressure_unit"], cache["temperature_unit"],
                )
            except Exception as exc:
                st.error(f"Color calculation error: {exc}")
                return

    z           = cache["z_grids"][cache["prop_key"]]
    z_color     = cache["z_grids"][color_prop_key]
    pressures   = cache["pressures"]
    temperatures = cache["temperatures"]
    color_prop_name, color_prop_unit = PROPERTIES[color_prop_key]

    fig = go.Figure(data=[go.Surface(
        x=pressures,
        y=temperatures,
        z=z,
        surfacecolor=z_color,
        customdata=z_color,
        colorscale=colorscale,
        colorbar=dict(title=f"{color_prop_name}<br>[{color_prop_unit}]", thickness=18),
        hovertemplate=(
            f"Pressure: %{{x:.3g}} {cache['pressure_unit']}<br>"
            f"Temperature: %{{y:.4g}} {cache['temp_label']}<br>"
            f"{prop_name}: %{{z:.5g}} {prop_unit}<br>"
            f"{color_prop_name}: %{{customdata:.5g}} {color_prop_unit}<extra></extra>"
        ),
    )])

    fig.update_layout(
        height=650,
        margin=dict(l=10, r=10, t=50, b=10),
        title=dict(text=f"{prop_name} [{prop_unit}]  ·  {cache['equation']}", font_size=14),
        scene=dict(
            xaxis_title=f"Pressure [{cache['pressure_unit']}]",
            yaxis_title=f"Temperature [{cache['temp_label']}]",
            zaxis_title=f"{prop_name} [{prop_unit}]",
            aspectmode="cube",
            camera=dict(eye=dict(x=-1.7, y=-1.6, z=0.4)),
        ),
    )

    st.plotly_chart(fig, width='stretch')
    st.caption("💡 Tip: Hold **Ctrl** while clicking and dragging to pan the 3D plot. Click and drag normally to rotate.")

    records = [
        {
            f"Pressure [{cache['pressure_unit']}]": float(P),
            f"Temperature [{cache['temp_label']}]": float(T),
            f"{prop_name} [{prop_unit}]":           z[i_T, i_P],
        }
        for i_T, T in enumerate(temperatures)
        for i_P, P in enumerate(pressures)
    ]
    dl_df = pd.DataFrame(records)

    st.download_button(
        label=f"Download {prop_name} data (CSV)",
        data=dl_df.to_csv(index=False).encode(),
        file_name=f"{cache['prop_key']}_{cache['equation']}_surface.csv",
        mime="text/csv",
        key="surf_dl_csv",
    )
