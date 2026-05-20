"""
Multi-point calculation component for the Gas Properties module.
Calculates all gas properties for a user-defined table of P&T points.
"""

import io

import pandas as pd
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

    # ── Input table ────────────────────────────────────────────────────────────
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

    calculate = st.button("Calculate", type="primary", key="multi_calc_btn")
    if not calculate:
        return

    # ── Drop incomplete rows ───────────────────────────────────────────────────
    rows = input_df.dropna(subset=[p_col, t_col])
    if rows.empty:
        st.warning("No valid rows in the table.")
        return

    # ── Run calculations ───────────────────────────────────────────────────────
    aga8 = pvtlib.AGA8(equation)
    records = []
    errors = []

    progress = st.progress(0, text="Calculating …")
    n = len(rows)

    for i, (_, row) in enumerate(rows.iterrows()):
        p = float(row[p_col])
        t = float(row[t_col])
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

    if errors:
        with st.expander(f"{len(errors)} row(s) failed"):
            for e in errors:
                st.error(e)

    if not records:
        st.error("All calculations failed.")
        return

    result_df = pd.DataFrame(records)

    st.success(f"Calculated {len(records)} point(s) using **{equation}**.")

    # ── Results table ──────────────────────────────────────────────────────────
    st.dataframe(result_df, width='stretch', hide_index=True)

    # ── CSV download ───────────────────────────────────────────────────────────
    buf = io.BytesIO()
    result_df.to_csv(buf, index=False)
    st.download_button(
        label="Download results (CSV)",
        data=buf.getvalue(),
        file_name=f"gas_properties_multipoint_{equation}.csv",
        mime="text/csv",
        key="multi_dl_csv",
    )
