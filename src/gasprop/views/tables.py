"""
Property Table component for the Gas Properties module.

Generates tables and interactive plots of gas properties over a
user-defined pressure–temperature grid, and allows export to PDF.
"""

from __future__ import annotations

import io

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pvtlib
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages


matplotlib.use("Agg")  # non-interactive backend, safe in Streamlit

PROPERTIES = {
    "rho":   ("Mass Density",               "kg/m³",        "{:.5f}"),
    "w":     ("Speed of Sound",             "m/s",          "{:.3f}"),
    "z":     ("Compressibility Factor",     "–",            "{:.6f}"),
    "cp":    ("Isobaric Heat Capacity",     "J/(mol·K)",    "{:.4f}"),
    "cv":    ("Isochoric Heat Capacity",    "J/(mol·K)",    "{:.4f}"),
    "kappa": ("Isentropic Exponent",        "–",            "{:.6f}"),
    "h":     ("Enthalpy",                   "J/mol",        "{:.4f}"),
    "s":     ("Entropy",                    "J/(mol·K)",    "{:.6f}"),
    "u":     ("Internal Energy",            "J/mol",        "{:.4f}"),
    "g":     ("Gibbs Energy",               "J/mol",        "{:.4f}"),
    "jt":    ("Joule-Thomson Coefficient",  "K/Pa",         "{:.8f}"),
    "mm":    ("Molar Mass",                 "g/mol",        "{:.4f}"),
}

_DEFAULT_PROPS = ["rho", "w", "z"]


def _build_dataframes(
    composition: dict,
    pressures: np.ndarray,
    temperatures: np.ndarray,
    selected_props: list[str],
    equation: str,
    pressure_unit: str,
    temperature_unit: str,
) -> dict[str, pd.DataFrame]:
    aga8 = pvtlib.AGA8(equation)

    temp_label = "°C" if temperature_unit == "C" else "K"
    p_labels = [f"{p:.3g} {pressure_unit}" for p in pressures]
    t_labels = [f"{t:.4g} {temp_label}" for t in temperatures]

    data: dict[str, dict] = {prop: {} for prop in selected_props}

    for T in temperatures:
        row: dict[str, list] = {prop: [] for prop in selected_props}
        for P in pressures:
            result = aga8.calculate_from_PT(
                composition=composition,
                pressure=float(P),
                temperature=float(T),
                pressure_unit=pressure_unit,
                temperature_unit=temperature_unit,
            )
            for prop in selected_props:
                row[prop].append(result[prop])

        t_key = f"{T:.4g} {temp_label}"
        for prop in selected_props:
            data[prop][t_key] = row[prop]

    dfs: dict[str, pd.DataFrame] = {}
    for prop in selected_props:
        df = pd.DataFrame(data[prop], index=p_labels).T
        df.index = t_labels
        df.columns = p_labels
        dfs[prop] = df

    return dfs


def _make_pdf_page(
    df: pd.DataFrame,
    pressures: np.ndarray,
    temperatures: np.ndarray,
    prop_key: str,
    pressure_unit: str,
    temperature_unit: str,
    equation: str,
    component_label: str,
) -> plt.Figure:
    name, unit, fmt = PROPERTIES[prop_key]
    temp_label = "°C" if temperature_unit == "C" else "K"
    title = (
        f"{component_label}  ·  {name}  [{unit}]  ·  {equation}"
    )

    fig = plt.figure(figsize=(11.69, 8.27))
    fig.suptitle(title, fontsize=12, fontweight="bold", y=0.98)

    ax_tbl = fig.add_axes([0.02, 0.52, 0.96, 0.41])
    ax_tbl.axis("off")
    cell_text = [[fmt.format(v) for v in row] for row in df.values]
    tbl = ax_tbl.table(
        cellText=cell_text,
        rowLabels=df.index.tolist(),
        colLabels=df.columns.tolist(),
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7.5)
    tbl.auto_set_column_width(col=list(range(-1, len(df.columns))))

    ax_plot = fig.add_axes([0.08, 0.06, 0.82, 0.38])
    colors = plt.cm.viridis(np.linspace(0, 0.85, len(temperatures)))
    for i, (T, color) in enumerate(zip(temperatures, colors)):
        t_key = f"{T:.4g} {temp_label}"
        ax_plot.plot(
            pressures,
            df.loc[t_key].values,
            marker="o",
            markersize=4,
            color=color,
            label=f"{T:.4g} {temp_label}",
        )
    ax_plot.set_xlabel(f"Pressure [{pressure_unit}]", fontsize=9)
    ax_plot.set_ylabel(f"{name} [{unit}]", fontsize=9)
    ax_plot.legend(
        title="Temperature",
        loc="upper left",
        bbox_to_anchor=(1.01, 1),
        fontsize=7,
        title_fontsize=8,
    )
    ax_plot.grid(True, linestyle="--", alpha=0.5)
    ax_plot.tick_params(labelsize=8)

    return fig


def _build_pdf(
    dfs: dict[str, pd.DataFrame],
    pressures: np.ndarray,
    temperatures: np.ndarray,
    selected_props: list[str],
    pressure_unit: str,
    temperature_unit: str,
    equation: str,
    component_label: str,
) -> bytes:
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        for prop in selected_props:
            fig = _make_pdf_page(
                dfs[prop],
                pressures,
                temperatures,
                prop,
                pressure_unit,
                temperature_unit,
                equation,
                component_label,
            )
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    buf.seek(0)
    return buf.read()


def render(composition: dict | None):
    st.subheader("Property Tables")
    st.caption(
        "Generate gas property tables and plots over a pressure–temperature grid. "
        "Tables can be exported as a multi-page PDF report."
    )

    if composition is None:
        return

    equation = st.selectbox("AGA8 equation", ["GERG-2008", "DETAIL"], index=0, key="table_eos")

    st.markdown("**Pressure Range**")
    pu_col, _ = st.columns([1, 2])
    pressure_unit = pu_col.selectbox("Pressure unit", ["bara", "barg", "kPa", "MPa"], index=0, key="table_p_unit")
    cp1, cp2, cp3 = st.columns(3)
    p_min  = cp1.number_input("Min",  value=1.0,   min_value=0.0,  step=5.0,  format="%.2f", key="table_p_min")
    p_max  = cp2.number_input("Max",  value=200.0, min_value=0.0,  step=5.0,  format="%.2f", key="table_p_max")
    p_step = cp3.number_input("Step", value=5.0,   min_value=0.01, step=1.0,  format="%.2f", key="table_p_step")

    st.markdown("**Temperature Range**")
    tu_col, _ = st.columns([1, 2])
    temperature_unit = tu_col.selectbox(
        "Temperature unit", ["C", "K"], index=0, key="table_t_unit",
        format_func=lambda x: "°C" if x == "C" else "K",
    )
    temp_label = "°C" if temperature_unit == "C" else "K"
    t_default_min = 0.0   if temperature_unit == "C" else 273.15
    t_default_max = 100.0 if temperature_unit == "C" else 373.15
    ct1, ct2, ct3 = st.columns(3)
    t_min  = ct1.number_input(f"Min [{temp_label}]",  value=t_default_min, step=5.0, format="%.1f", key="table_t_min")
    t_max  = ct2.number_input(f"Max [{temp_label}]",  value=t_default_max, step=5.0, format="%.1f", key="table_t_max")
    t_step = ct3.number_input(f"Step [{temp_label}]", value=5.0, min_value=0.1, step=1.0, format="%.1f", key="table_t_step")

    st.markdown("**Properties to calculate**")
    prop_options = {k: f"{v[0]}  [{v[1]}]" for k, v in PROPERTIES.items()}
    selected_props = st.multiselect(
        "Select properties",
        options=list(prop_options.keys()),
        default=_DEFAULT_PROPS,
        format_func=lambda k: prop_options[k],
        key="table_props",
        label_visibility="collapsed",
    )

    generate = st.button("Generate Tables", type="primary", key="table_gen_btn")

    if not generate:
        return

    if not selected_props:
        st.warning("Select at least one property to calculate.")
        return

    if p_min >= p_max:
        st.error("Pressure min must be less than max.")
        return

    if t_min >= t_max:
        st.error("Temperature min must be less than max.")
        return

    pressures    = np.arange(p_min, p_max    + p_step * 0.5, p_step)
    temperatures = np.arange(t_min, t_max    + t_step * 0.5, t_step)

    n_calcs = len(pressures) * len(temperatures)
    if n_calcs > 2000:
        st.error(f"Grid too large ({n_calcs} points). Reduce the range or increase the step size.")
        return

    non_zero = {k: v for k, v in composition.items() if v > 0}
    if len(non_zero) == 1:
        comp_key = next(iter(non_zero))
        from gasprop.composition_input import COMPONENTS
        component_label = COMPONENTS.get(comp_key, comp_key)
    else:
        component_label = "Gas Mixture"

    progress = st.progress(0, text="Calculating…")
    try:
        dfs = _build_dataframes(
            composition, pressures, temperatures,
            selected_props, equation, pressure_unit, temperature_unit,
        )
    except Exception as exc:
        st.error(f"Calculation error: {exc}")
        progress.empty()
        return

    progress.progress(1.0, text="Done")
    progress.empty()

    for prop in selected_props:
        name, unit, fmt = PROPERTIES[prop]
        df = dfs[prop]

        with st.expander(f"**{name}**  [{unit}]", expanded=True):
            fig = go.Figure()
            colors = [
                f"hsl({int(i * 240 / max(len(temperatures) - 1, 1))}, 70%, 50%)"
                for i in range(len(temperatures))
            ]
            for i, T in enumerate(temperatures):
                t_key = f"{T:.4g} {temp_label}"
                fig.add_trace(go.Scatter(
                    x=pressures,
                    y=df.loc[t_key].values,
                    mode="lines+markers",
                    name=t_key,
                    line=dict(color=colors[i]),
                    marker=dict(size=5),
                ))
            fig.update_layout(
                xaxis_title=f"Pressure [{pressure_unit}]",
                yaxis_title=f"{name} [{unit}]",
                legend_title="Temperature",
                height=400,
                margin=dict(l=60, r=20, t=30, b=50),
            )
            st.plotly_chart(fig, width='stretch')

            display_df = df.copy().map(lambda v: fmt.format(v))
            st.dataframe(display_df, width='stretch')

            csv_bytes = df.to_csv().encode()
            st.download_button(
                label=f"Download {name} table (CSV)",
                data=csv_bytes,
                file_name=f"{prop}_{equation}.csv",
                mime="text/csv",
                key=f"dl_csv_{prop}",
            )

    st.divider()
    st.markdown("### Export Report")

    with st.spinner("Building PDF report…"):
        pdf_bytes = _build_pdf(
            dfs, pressures, temperatures,
            selected_props, pressure_unit, temperature_unit,
            equation, component_label,
        )

    st.download_button(
        label="Download PDF Report (all properties)",
        data=pdf_bytes,
        file_name=f"gas_properties_{equation}.pdf",
        mime="application/pdf",
        type="primary",
    )
