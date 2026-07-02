"""
Multi-point calculation component for the Gas Properties module.
Calculates all gas properties for a user-defined table of P&T points.
"""

import io

import numpy as np
import pandas as pd
import plotly.express as px
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

_DEFAULT_POINTS = pd.DataFrame({
    "Pressure": [1.0, 10.0, 50.0, 100.0, 200.0],
    "Temperature": [15.0, 15.0, 15.0, 15.0, 15.0],
})
_STATE_MULTI = "gp_multi_result"


def _build_points_from_range(
    p_min: float,
    p_max: float,
    p_step: float,
    t_min: float,
    t_max: float,
    t_step: float,
) -> list[tuple[float, float]]:
    pressures = np.arange(p_min, p_max + 0.5 * p_step, p_step)
    temperatures = np.arange(t_min, t_max + 0.5 * t_step, t_step)
    return [(float(p), float(t)) for t in temperatures for p in pressures]


def _plot_results(df: pd.DataFrame) -> None:
    if df.empty:
        return

    st.markdown("#### Visualisation")
    plot_mode = st.radio(
        "Plot type",
        options=["2D", "3D"],
        horizontal=True,
        key="multi_plot_mode",
    )

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if len(numeric_cols) < 2:
        st.info("Need at least two numeric columns for plotting.")
        return

    pressure_col = next((c for c in df.columns if c.startswith("Pressure [")), None)
    temperature_col = next((c for c in df.columns if c.startswith("Temperature [")), None)
    density_col = next((c for c in df.columns if c.startswith("Mass Density [")), None)

    default_x = pressure_col if pressure_col in numeric_cols else numeric_cols[0]
    default_y = density_col if density_col in numeric_cols else (temperature_col if temperature_col in numeric_cols else numeric_cols[1])

    default_x_idx = numeric_cols.index(default_x)
    default_y_idx = numeric_cols.index(default_y)

    color_options = ["None"] + numeric_cols
    default_color = temperature_col if temperature_col in color_options else "None"
    default_color_idx = color_options.index(default_color)

    color_scale_options = ["Viridis", "Plasma", "Inferno", "Magma", "Cividis", "Turbo"]
    default_color_scale_idx = color_scale_options.index("Turbo")

    if plot_mode == "2D":
        c1, c2, c3, c4 = st.columns(4)
        x_col = c1.selectbox("X axis", numeric_cols, index=default_x_idx, key="multi_plot2d_x")
        y_col = c2.selectbox("Y axis", numeric_cols, index=default_y_idx, key="multi_plot2d_y")
        color_col = c3.selectbox("Color by", options=color_options, index=default_color_idx, key="multi_plot2d_color")
        color_scale = c4.selectbox("Color palette", options=color_scale_options, index=default_color_scale_idx, key="multi_plot2d_colorscale")

        fig = px.scatter(
            df,
            x=x_col,
            y=y_col,
            color=None if color_col == "None" else color_col,
            color_continuous_scale=color_scale if color_col != "None" else None,
            hover_data=[col for col in ["Pressure [bara]", "Pressure [barg]", "Pressure [kPa]", "Pressure [MPa]", "Temperature [°C]", "Temperature [K]"] if col in df.columns],
        )
        fig.update_layout(height=520)
        st.plotly_chart(fig, width='stretch')
    else:
        if len(numeric_cols) < 3:
            st.info("Need at least three numeric columns for 3D plot.")
            return

        default_z = temperature_col if temperature_col in numeric_cols else numeric_cols[2]
        default_z_idx = numeric_cols.index(default_z)

        c1, c2, c3, c4, c5 = st.columns(5)
        x_col = c1.selectbox("X axis", numeric_cols, index=default_x_idx, key="multi_plot3d_x")
        y_col = c2.selectbox("Y axis", numeric_cols, index=default_y_idx, key="multi_plot3d_y")
        z_col = c3.selectbox("Z axis", numeric_cols, index=default_z_idx, key="multi_plot3d_z")
        color_col = c4.selectbox("Color by", options=color_options, index=default_color_idx, key="multi_plot3d_color")
        color_scale = c5.selectbox("Color palette", options=color_scale_options, index=default_color_scale_idx, key="multi_plot3d_colorscale")

        fig = px.scatter_3d(
            df,
            x=x_col,
            y=y_col,
            z=z_col,
            color=None if color_col == "None" else color_col,
            color_continuous_scale=color_scale if color_col != "None" else None,
            hover_data=[col for col in ["Pressure [bara]", "Pressure [barg]", "Pressure [kPa]", "Pressure [MPa]", "Temperature [°C]", "Temperature [K]"] if col in df.columns],
        )
        fig.update_layout(height=650)
        st.plotly_chart(fig, width='stretch')


def render(composition: dict | None) -> None:
    """Render the multi-point P&T calculation UI."""

    st.subheader("Multi-Point Calculation")
    st.caption("Calculate gas properties at multiple pressure–temperature points in one run.")

    if composition is None:
        return

    # ── Settings ───────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    equation = c1.selectbox(
        "AGA8 equation", ["GERG-2008", "DETAIL"], index=0, key="multi_eos",
        help="GERG-2008 is recommended for natural gas mixtures.",
    )
    pressure_unit = c2.selectbox(
        "Pressure unit", ["bara", "barg", "kPa", "MPa"], index=0, key="multi_p_unit",
    )
    temperature_unit = c3.selectbox(
        "Temperature unit", ["C", "K"], index=0, key="multi_t_unit",
        format_func=lambda x: "°C" if x == "C" else "K",
    )
    temp_label = "°C" if temperature_unit == "C" else "K"

    mode = st.radio(
        "Input mode",
        options=["Input table", "Pressure/temperature ranges"],
        horizontal=True,
        key="multi_input_mode",
    )

    points: list[tuple[float, float]] = []

    if mode == "Input table":
        st.markdown(f"#### Operating Points  ·  Pressure [{pressure_unit}]  ·  Temperature [{temp_label}]")
        st.caption("Add, edit or delete rows. Click Calculate when ready.")

        input_df = st.data_editor(
            _DEFAULT_POINTS.rename(columns={
                "Pressure": f"Pressure [{pressure_unit}]",
                "Temperature": f"Temperature [{temp_label}]",
            }),
            key="multi_input_table",
            width='stretch',
            hide_index=True,
            num_rows="dynamic",
            column_config={
                f"Pressure [{pressure_unit}]": st.column_config.NumberColumn(
                    f"Pressure [{pressure_unit}]",
                    min_value=0.0,
                    step=0.1,
                    format="%.3f",
                ),
                f"Temperature [{temp_label}]": st.column_config.NumberColumn(
                    f"Temperature [{temp_label}]",
                    step=0.5,
                    format="%.2f",
                ),
            },
        )

        p_col = f"Pressure [{pressure_unit}]"
        t_col = f"Temperature [{temp_label}]"
        rows = input_df.dropna(subset=[p_col, t_col])
        points = [(float(r[p_col]), float(r[t_col])) for _, r in rows.iterrows()]
    else:
        st.markdown("#### Pressure range")
        cp1, cp2, cp3 = st.columns(3)
        p_min = cp1.number_input("P min", min_value=0.0, value=5.0, step=1.0, format="%.3f", key="multi_pmin")
        p_max = cp2.number_input("P max", min_value=0.0, value=200.0, step=1.0, format="%.3f", key="multi_pmax")
        p_step = cp3.number_input("P step", min_value=0.01, value=5.0, step=1.0, format="%.3f", key="multi_pstep")

        st.markdown(f"#### Temperature range [{temp_label}]")
        ct1, ct2, ct3 = st.columns(3)
        t_floor = -273.15 if temperature_unit == "C" else 0.0
        t_default_min = 0.0 if temperature_unit == "C" else 273.15
        t_default_max = 100.0 if temperature_unit == "C" else 373.15
        t_min = ct1.number_input("T min", min_value=t_floor, value=t_default_min, step=1.0, format="%.3f", key="multi_tmin")
        t_max = ct2.number_input("T max", min_value=t_floor, value=t_default_max, step=1.0, format="%.3f", key="multi_tmax")
        t_step = ct3.number_input("T step", min_value=0.01, value=5.0, step=1.0, format="%.3f", key="multi_tstep")

        if p_min >= p_max:
            st.error("Pressure min must be lower than pressure max.")
            return
        if t_min >= t_max:
            st.error("Temperature min must be lower than temperature max.")
            return

        points = _build_points_from_range(p_min, p_max, p_step, t_min, t_max, t_step)
        if len(points) > 3000:
            st.error(f"Range produces too many points ({len(points)}). Reduce ranges or increase step sizes.")
            return

    cached = st.session_state.get(_STATE_MULTI)
    has_cache = cached is not None
    run_label = "Calculate" if not has_cache else "Re-calculate"
    calculate = st.button(run_label, type="primary", key="multi_calc_btn")

    if calculate:
        if not points:
            st.warning("No valid pressure/temperature points found.")
        else:
            # ── Run calculations ───────────────────────────────────────────────
            aga8 = pvtlib.AGA8(equation)
            records = []
            errors = []

            progress = st.progress(0, text="Calculating …")
            n = len(points)

            p_col = f"Pressure [{pressure_unit}]"
            t_col = f"Temperature [{temp_label}]"

            for i, (p, t) in enumerate(points):
                try:
                    res = aga8.calculate_from_PT(
                        composition=composition,
                        pressure=p,
                        temperature=t,
                        pressure_unit=pressure_unit,
                        temperature_unit=temperature_unit,
                    )
                    record = {p_col: p, t_col: t}
                    for key, (name, unit) in PROPERTIES.items():
                        record[f"{name} [{unit}]"] = res[key]
                    records.append(record)
                except Exception as exc:
                    errors.append(f"Row {i + 1} (P={p}, T={t}): {exc}")
                progress.progress((i + 1) / n, text=f"Calculating … {i + 1}/{n}")

            progress.empty()

            if not records:
                st.error("All calculations failed.")
            else:
                st.session_state[_STATE_MULTI] = {
                    "result_df": pd.DataFrame(records),
                    "errors": errors,
                    "equation": equation,
                }

    state = st.session_state.get(_STATE_MULTI)
    if state is None:
        return

    result_df = state["result_df"]
    errors = state["errors"]
    result_equation = state["equation"]

    if errors:
        with st.expander(f"{len(errors)} row(s) failed"):
            for e in errors:
                st.error(e)

    if not calculate:
        st.caption("Showing most recent multi-point results. Click Re-calculate to update.")

    st.success(f"Calculated {len(result_df)} point(s) using **{result_equation}**.")

    # ── Results table ──────────────────────────────────────────────────────────
    st.dataframe(result_df, width='stretch', hide_index=True)

    # ── Plotting ───────────────────────────────────────────────────────────────
    _plot_results(result_df)

    # ── CSV download ───────────────────────────────────────────────────────────
    buf = io.BytesIO()
    result_df.to_csv(buf, index=False)
    st.download_button(
        label="Download results (CSV)",
        data=buf.getvalue(),
        file_name=f"gas_properties_multipoint_{result_equation}.csv",
        mime="text/csv",
        key="multi_dl_csv",
    )
