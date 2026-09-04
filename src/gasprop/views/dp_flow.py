"""
DP Flow Meter tab for the Gas Properties module.

Calculates gas flow rates through Venturi, orifice and V-cone differential-pressure
meters using ``pvtlib`` ISO 5167 models, with AGA8 (GERG-2008 / DETAIL) supplying the
upstream density, isentropic exponent and standard density.

Three workflows are offered:
  * Single point   -- one dP / P / T point with a full result breakdown
  * Multi-point    -- a table of dP / P / T points with plots and CSV export
  * Sizing         -- solve for the dP that gives a target flow rate
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from ..dp_flow import (
    DEFAULT_C_V_CONE,
    DEFAULT_C_VENTURI,
    ISO_LIMITS,
    METER_TYPES,
    ORIFICE_TAPPINGS,
    VENTURI_C_PRESETS,
    DPFlowError,
    DPFlowResult,
    MeterGeometry,
    calculate_dp_flow,
    calculate_gas_state,
    solve_dp_for_mass_flow,
    solve_dp_for_std_volume_flow,
)

_DIAGRAM_DIR = Path(__file__).resolve().parents[3] / "assets" / "dp_meters"

DIAGRAMS: dict[str, str] = {
    "Venturi": "venturi.svg",
    "Orifice": "orifice.svg",
    "V-cone": "v_cone.svg",
}

METER_DESCRIPTIONS: dict[str, str] = {
    "Venturi": (
        "Venturi tube according to **ISO 5167-4:2022**. The discharge coefficient is a fixed value "
        "(0.984 for an as-cast convergent section) unless the meter is calibrated."
    ),
    "Orifice": (
        "Orifice plate according to **ISO 5167-2:2022**. The discharge coefficient is solved "
        "iteratively with the Reader-Harris/Gallagher equation, which needs the Reynolds number "
        "and therefore the gas viscosity."
    ),
    "V-cone": (
        "Cone meter according to **ISO 5167-5:2022**. The uncalibrated discharge coefficient is 0.82, "
        "but cone meters are normally flow calibrated — enter the calibrated value when available."
    ),
}

BORE_LABELS: dict[str, str] = {
    "Venturi": "Throat diameter d [mm]",
    "Orifice": "Orifice bore d [mm]",
    "V-cone": "Cone diameter d\u1d04 at the beta edge [mm]",
}

_DEFAULT_POINTS = pd.DataFrame(
    {
        "dP [mbar]": [100.0, 250.0, 500.0, 800.0],
        "Pressure": [60.0, 60.0, 60.0, 60.0],
        "Temperature": [20.0, 20.0, 20.0, 20.0],
    }
)

TARGET_BASES: dict[str, str] = {
    "Standard volume flow [Sm³/h]": "sm3_h",
    "Standard volume flow [Sm³/d]": "sm3_d",
    "Mass flow [kg/h]": "kg_h",
}


@lru_cache(maxsize=8)
def _diagram_data_uri(file_name: str) -> str | None:
    path = _DIAGRAM_DIR / file_name
    if not path.exists():
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _render_diagram(meter_type: str) -> None:
    """Render the parameter diagram for the selected meter type."""
    file_name = DIAGRAMS.get(meter_type)
    if file_name is None:
        return
    data_uri = _diagram_data_uri(file_name)
    if data_uri is None:
        return
    st.markdown(
        f'<img src="{data_uri}" alt="{meter_type} meter parameter diagram" '
        'style="width:100%;max-width:760px;display:block;margin:0.2rem auto 0.6rem auto;" />',
        unsafe_allow_html=True,
    )


def _meter_inputs() -> tuple[MeterGeometry | None, str]:
    """Render meter geometry inputs and return the geometry plus the meter type."""
    meter_type = st.selectbox("Meter type", list(METER_TYPES), index=0, key="dpf_meter_type")

    st.caption(METER_DESCRIPTIONS[meter_type])
    _render_diagram(meter_type)

    c1, c2 = st.columns(2)
    pipe_diameter = c1.number_input(
        "Pipe diameter D [mm]",
        min_value=0.1, max_value=5000.0, value=200.0, step=1.0, format="%.3f",
        key="dpf_pipe_diameter",
        help="Internal pipe diameter at the upstream pressure tapping.",
    )
    bore_diameter = c2.number_input(
        BORE_LABELS[meter_type],
        min_value=0.1, max_value=5000.0, value=120.0, step=1.0, format="%.3f",
        key="dpf_bore_diameter",
        help=(
            "Cone diameter in the plane of the beta edge."
            if meter_type == "V-cone"
            else "Throat / bore diameter of the primary element."
        ),
    )

    tapping = "corner"
    if meter_type == "Orifice":
        tapping = st.selectbox(
            "Orifice tapping", list(ORIFICE_TAPPINGS), index=0, key="dpf_tapping",
            help="Tapping arrangement used by the Reader-Harris/Gallagher discharge coefficient.",
        )

    try:
        geometry = MeterGeometry(
            meter_type=meter_type,
            pipe_diameter_mm=float(pipe_diameter),
            bore_diameter_mm=float(bore_diameter),
            tapping=tapping,
        )
    except DPFlowError as exc:
        st.error(str(exc))
        return None, meter_type

    beta_min, beta_max = ISO_LIMITS[meter_type]["beta"]
    st.markdown(f"**Beta (β):** {geometry.beta:.4f}  —  ISO 5167 range of use: {beta_min:.2f}–{beta_max:.2f}")
    return geometry, meter_type


def _coefficient_inputs(meter_type: str) -> tuple[float | None, float | None]:
    """Render discharge coefficient / expansibility overrides."""
    st.markdown("#### Discharge coefficient and expansibility")
    c1, c2 = st.columns(2)

    with c1:
        if meter_type == "Orifice":
            c_mode = st.radio(
                "Discharge coefficient C",
                ["Reader-Harris/Gallagher (ISO 5167-2)", "Manual"],
                index=0, key="dpf_c_mode_orifice", horizontal=False,
            )
            if c_mode == "Manual":
                discharge_coefficient = st.number_input(
                    "C [-]", min_value=0.1, max_value=1.5, value=0.6, step=0.001, format="%.5f",
                    key="dpf_c_manual_orifice",
                )
            else:
                discharge_coefficient = None
        elif meter_type == "Venturi":
            preset_labels = list(VENTURI_C_PRESETS.keys()) + ["Manual"]
            c_mode = st.selectbox("Discharge coefficient C", preset_labels, index=0, key="dpf_c_mode_venturi")
            if c_mode == "Manual":
                discharge_coefficient = st.number_input(
                    "C [-]", min_value=0.1, max_value=1.5, value=DEFAULT_C_VENTURI, step=0.001, format="%.5f",
                    key="dpf_c_manual_venturi",
                )
            elif VENTURI_C_PRESETS[c_mode] == DEFAULT_C_VENTURI:
                # The as-cast preset is the ISO 5167-4 default the range checks assume,
                # so it is passed as "not overridden" rather than as a fixed coefficient.
                discharge_coefficient = None
            else:
                discharge_coefficient = VENTURI_C_PRESETS[c_mode]
        else:
            c_mode = st.radio(
                "Discharge coefficient C",
                ["ISO 5167-5 default (0.82)", "Manual (calibrated)"],
                index=0, key="dpf_c_mode_vcone",
            )
            if c_mode == "Manual (calibrated)":
                discharge_coefficient = st.number_input(
                    "C [-]", min_value=0.1, max_value=1.5, value=DEFAULT_C_V_CONE, step=0.001, format="%.5f",
                    key="dpf_c_manual_vcone",
                )
            else:
                discharge_coefficient = None

    with c2:
        epsilon_mode = st.radio(
            "Expansibility ε",
            ["Calculated from AGA8 κ", "Manual"],
            index=0, key="dpf_eps_mode",
            help="The expansibility correlation depends on the meter type, beta, dP/p₁ and the isentropic exponent.",
        )
        if epsilon_mode == "Manual":
            expansibility = st.number_input(
                "ε [-]", min_value=0.1, max_value=1.0, value=1.0, step=0.0001, format="%.6f",
                key="dpf_eps_manual",
            )
        else:
            expansibility = None

    return discharge_coefficient, expansibility


def _process_inputs(key_suffix: str) -> tuple[str, str, str]:
    """Render pressure/temperature unit and AGA8 equation inputs."""
    c1, c2, c3 = st.columns(3)
    equation = c1.selectbox(
        "AGA8 equation", ["GERG-2008", "DETAIL"], index=0, key=f"dpf_eos_{key_suffix}",
        help="GERG-2008 is recommended for natural gas mixtures.",
    )
    pressure_unit = c2.selectbox(
        "Pressure unit", ["bara", "barg", "kPa", "MPa"], index=0, key=f"dpf_p_unit_{key_suffix}"
    )
    temperature_unit = c3.selectbox(
        "Temperature unit", ["C", "K"], index=0, key=f"dpf_t_unit_{key_suffix}",
        format_func=lambda x: "°C" if x == "C" else "K",
    )
    return equation, pressure_unit, temperature_unit


def _viscosity_inputs(key_suffix: str) -> float | None:
    """Render the viscosity source selector and return a manual viscosity if chosen."""
    mode = st.radio(
        "Dynamic viscosity source",
        ["Automatic (NeqSim)", "Manual"],
        index=0, key=f"dpf_visc_mode_{key_suffix}", horizontal=True,
        help=(
            "AGA8 does not model viscosity. NeqSim (SRK) is used for the gas-phase viscosity, which "
            "is needed for the Reynolds number and the orifice discharge coefficient."
        ),
    )
    if mode == "Manual":
        return float(
            st.number_input(
                "Dynamic viscosity μ [Pa·s]",
                min_value=1e-9, max_value=1.0, value=1.2e-5, step=1e-6, format="%.3e",
                key=f"dpf_visc_manual_{key_suffix}",
            )
        )
    return None


def _result_rows(result: DPFlowResult) -> list[dict[str, str]]:
    gas = result.gas_state
    rows = [
        {"Quantity": "Mass flow", "Value": f"{result.mass_flow_kg_h:.4f}", "Unit": "kg/h"},
        {"Quantity": "Actual volume flow", "Value": f"{result.volume_flow_m3_h:.4f}", "Unit": "m³/h"},
        {"Quantity": "Standard volume flow", "Value": f"{result.std_volume_flow_sm3_h:.3f}", "Unit": "Sm³/h"},
        {"Quantity": "Standard volume flow", "Value": f"{result.std_volume_flow_sm3_d:.2f}", "Unit": "Sm³/d"},
        {"Quantity": "Pipe velocity", "Value": f"{result.velocity_m_s:.4f}", "Unit": "m/s"},
        {"Quantity": "Beta", "Value": f"{result.beta:.6f}", "Unit": "-"},
        {
            "Quantity": f"Discharge coefficient C ({result.discharge_coefficient_source})",
            "Value": f"{result.discharge_coefficient:.6f}",
            "Unit": "-",
        },
        {
            "Quantity": f"Expansibility ε ({result.expansibility_source})",
            "Value": f"{result.expansibility:.6f}",
            "Unit": "-",
        },
        {
            "Quantity": "Reynolds number",
            "Value": "n/a" if result.reynolds_number is None else f"{result.reynolds_number:.4e}",
            "Unit": "-",
        },
        {"Quantity": "Differential pressure", "Value": f"{result.differential_pressure_mbar:.4f}", "Unit": "mbar"},
        {"Quantity": "Pressure ratio p₂/p₁", "Value": f"{result.pressure_ratio:.6f}", "Unit": "-"},
        {"Quantity": f"Upstream density ρ₁ ({gas.equation})", "Value": f"{gas.density_kg_m3:.5f}", "Unit": "kg/m³"},
        {"Quantity": "Standard density", "Value": f"{gas.standard_density_kg_sm3:.6f}", "Unit": "kg/Sm³"},
        {"Quantity": "Isentropic exponent κ", "Value": f"{gas.kappa:.6f}", "Unit": "-"},
        {"Quantity": "Compressibility factor Z", "Value": f"{gas.z:.6f}", "Unit": "-"},
        {"Quantity": "Molar mass", "Value": f"{gas.molar_mass_g_mol:.4f}", "Unit": "g/mol"},
        {"Quantity": "Speed of sound", "Value": f"{gas.speed_of_sound_m_s:.3f}", "Unit": "m/s"},
        {
            "Quantity": f"Dynamic viscosity μ ({gas.viscosity_source})",
            "Value": "n/a" if gas.viscosity_pa_s is None else f"{gas.viscosity_pa_s:.6e}",
            "Unit": "Pa·s",
        },
        {"Quantity": "Upstream pressure p₁", "Value": f"{gas.pressure_bara:.5f}", "Unit": "bara"},
        {"Quantity": "Upstream temperature T₁", "Value": f"{gas.temperature_c:.4f}", "Unit": "°C"},
    ]
    return rows


def _render_warnings(result: DPFlowResult) -> None:
    if result.warnings:
        st.warning(
            "**ISO 5167 range-of-use checks:**\n\n"
            + "\n".join(f"- {message}" for message in result.warnings)
        )
    else:
        st.success("All ISO 5167 range-of-use checks passed for the selected meter type.")


def _render_single_point(
    composition: dict,
    geometry: MeterGeometry,
    discharge_coefficient: float | None,
    expansibility: float | None,
) -> None:
    st.markdown("#### Operating conditions")
    equation, pressure_unit, temperature_unit = _process_inputs("single")

    c1, c2, c3 = st.columns(3)
    pressure = c1.number_input(
        f"Upstream pressure p₁ [{pressure_unit}]",
        min_value=0.0, max_value=1000.0, value=60.0, step=0.1, format="%.4f",
        key="dpf_pressure_single",
    )
    temperature = c2.number_input(
        f"Temperature T₁ [{'°C' if temperature_unit == 'C' else 'K'}]",
        min_value=-273.15 if temperature_unit == "C" else 0.0,
        max_value=2000.0, value=20.0, step=0.5, format="%.3f",
        key="dpf_temperature_single",
    )
    dp_mbar = c3.number_input(
        "Differential pressure Δp [mbar]",
        min_value=0.0, max_value=1_000_000.0, value=500.0, step=1.0, format="%.4f",
        key="dpf_dp_single",
    )

    viscosity = _viscosity_inputs("single")

    if not st.button("Calculate flow", type="primary", key="dpf_calc_single"):
        return

    try:
        gas_state = calculate_gas_state(
            composition,
            float(pressure),
            float(temperature),
            pressure_unit=pressure_unit,
            temperature_unit=temperature_unit,
            equation=equation,
            viscosity_pa_s=viscosity,
        )
        result = calculate_dp_flow(
            geometry,
            gas_state,
            float(dp_mbar),
            discharge_coefficient=discharge_coefficient,
            expansibility=expansibility,
        )
    except DPFlowError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # pragma: no cover - defensive UI guard
        st.error(f"Calculation failed: {exc}")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Mass flow [kg/h]", f"{result.mass_flow_kg_h:,.1f}")
    m2.metric("Standard volume [Sm³/h]", f"{result.std_volume_flow_sm3_h:,.1f}")
    m3.metric("Standard volume [Sm³/d]", f"{result.std_volume_flow_sm3_d:,.0f}")
    m4.metric("Pipe velocity [m/s]", f"{result.velocity_m_s:,.3f}")

    _render_warnings(result)

    results_df = pd.DataFrame(_result_rows(result))
    st.dataframe(results_df, width="stretch", hide_index=True)

    st.download_button(
        "Download results (CSV)",
        data=results_df.to_csv(index=False).encode(),
        file_name=(
            f"dp_flow_{geometry.meter_type.lower().replace('-', '_')}_"
            f"{dp_mbar:.4g}mbar_{pressure:.4g}{pressure_unit}.csv"
        ),
        mime="text/csv",
        key="dpf_dl_single",
    )


def _render_multi_point(
    composition: dict,
    geometry: MeterGeometry,
    discharge_coefficient: float | None,
    expansibility: float | None,
) -> None:
    st.markdown("#### Operating points")
    equation, pressure_unit, temperature_unit = _process_inputs("multi")
    viscosity = _viscosity_inputs("multi")

    points = st.data_editor(
        _DEFAULT_POINTS,
        num_rows="dynamic",
        width="stretch",
        key="dpf_points",
        column_config={
            "dP [mbar]": st.column_config.NumberColumn("Δp [mbar]", min_value=0.0, format="%.4f"),
            "Pressure": st.column_config.NumberColumn(f"p₁ [{pressure_unit}]", format="%.4f"),
            "Temperature": st.column_config.NumberColumn(
                f"T₁ [{'°C' if temperature_unit == 'C' else 'K'}]", format="%.4f"
            ),
        },
    )

    if not st.button("Calculate all points", type="primary", key="dpf_calc_multi"):
        return

    temperature_column = f"T₁ [{'°C' if temperature_unit == 'C' else 'K'}]"
    rows: list[dict[str, float | str]] = []
    all_warnings: list[str] = []
    for _, point in points.iterrows():
        dp_value = point.get("dP [mbar]")
        p_value = point.get("Pressure")
        t_value = point.get("Temperature")
        if pd.isna(dp_value) or pd.isna(p_value) or pd.isna(t_value):
            continue
        try:
            gas_state = calculate_gas_state(
                composition,
                float(p_value),
                float(t_value),
                pressure_unit=pressure_unit,
                temperature_unit=temperature_unit,
                equation=equation,
                viscosity_pa_s=viscosity,
            )
            result = calculate_dp_flow(
                geometry,
                gas_state,
                float(dp_value),
                discharge_coefficient=discharge_coefficient,
                expansibility=expansibility,
            )
        except Exception as exc:
            rows.append(
                {
                    "Δp [mbar]": float(dp_value),
                    f"p₁ [{pressure_unit}]": float(p_value),
                    temperature_column: float(t_value),
                    "Error": str(exc),
                }
            )
            continue

        for message in result.warnings:
            if message not in all_warnings:
                all_warnings.append(message)

        rows.append(
            {
                "Δp [mbar]": float(dp_value),
                f"p₁ [{pressure_unit}]": float(p_value),
                temperature_column: float(t_value),
                "ρ₁ [kg/m³]": gas_state.density_kg_m3,
                "Mass flow [kg/h]": result.mass_flow_kg_h,
                "Actual volume [m³/h]": result.volume_flow_m3_h,
                "Std volume [Sm³/h]": result.std_volume_flow_sm3_h,
                "Std volume [Sm³/d]": result.std_volume_flow_sm3_d,
                "Velocity [m/s]": result.velocity_m_s,
                "C [-]": result.discharge_coefficient,
                "ε [-]": result.expansibility,
                "Re [-]": result.reynolds_number,
            }
        )

    if not rows:
        st.warning("No valid operating points to calculate. Fill in Δp, pressure and temperature.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True)

    if all_warnings:
        st.warning(
            "**ISO 5167 range-of-use checks:**\n\n"
            + "\n".join(f"- {message}" for message in all_warnings)
        )

    if "Std volume [Sm³/h]" in df.columns and len(df) > 1:
        plot_df = df.dropna(subset=["Std volume [Sm³/h]"])
        if not plot_df.empty:
            figure = px.line(
                plot_df,
                x="Δp [mbar]",
                y="Std volume [Sm³/h]",
                markers=True,
                title=f"{geometry.meter_type} — standard volume flow vs differential pressure",
            )
            st.plotly_chart(figure, width="stretch")

    st.download_button(
        "Download results (CSV)",
        data=df.to_csv(index=False).encode(),
        file_name=f"dp_flow_{geometry.meter_type.lower().replace('-', '_')}_multipoint.csv",
        mime="text/csv",
        key="dpf_dl_multi",
    )


def _render_sizing(
    composition: dict,
    geometry: MeterGeometry,
    discharge_coefficient: float | None,
    expansibility: float | None,
) -> None:
    st.caption(
        "Solve for the differential pressure that a given flow rate produces in the configured meter. "
        "Use this to check that the dP transmitter range fits the expected flow range."
    )

    st.markdown("#### Operating conditions")
    equation, pressure_unit, temperature_unit = _process_inputs("sizing")

    c1, c2 = st.columns(2)
    pressure = c1.number_input(
        f"Upstream pressure p₁ [{pressure_unit}]",
        min_value=0.0, max_value=1000.0, value=60.0, step=0.1, format="%.4f",
        key="dpf_pressure_sizing",
    )
    temperature = c2.number_input(
        f"Temperature T₁ [{'°C' if temperature_unit == 'C' else 'K'}]",
        min_value=-273.15 if temperature_unit == "C" else 0.0,
        max_value=2000.0, value=20.0, step=0.5, format="%.3f",
        key="dpf_temperature_sizing",
    )

    st.markdown("#### Target flow rate")
    c3, c4, c5 = st.columns(3)
    target_basis = c3.selectbox("Target basis", list(TARGET_BASES.keys()), index=0, key="dpf_target_basis")
    target_value = c4.number_input(
        "Target flow rate",
        min_value=0.0, max_value=1e12, value=100_000.0, step=1000.0, format="%.4f",
        key="dpf_target_value",
    )
    dp_max = c5.number_input(
        "Maximum Δp [mbar]",
        min_value=1.0, max_value=1_000_000.0, value=2000.0, step=100.0, format="%.2f",
        key="dpf_dp_max",
        help="Upper limit of the dP transmitter range, used as the search ceiling.",
    )

    viscosity = _viscosity_inputs("sizing")

    if not st.button("Solve for Δp", type="primary", key="dpf_calc_sizing"):
        return

    try:
        gas_state = calculate_gas_state(
            composition,
            float(pressure),
            float(temperature),
            pressure_unit=pressure_unit,
            temperature_unit=temperature_unit,
            equation=equation,
            viscosity_pa_s=viscosity,
        )
        basis = TARGET_BASES[target_basis]
        if basis == "kg_h":
            result = solve_dp_for_mass_flow(
                geometry,
                gas_state,
                float(target_value),
                discharge_coefficient=discharge_coefficient,
                expansibility=expansibility,
                dp_max_mbar=float(dp_max),
            )
        else:
            target_sm3_h = float(target_value) / (24.0 if basis == "sm3_d" else 1.0)
            result = solve_dp_for_std_volume_flow(
                geometry,
                gas_state,
                target_sm3_h,
                discharge_coefficient=discharge_coefficient,
                expansibility=expansibility,
                dp_max_mbar=float(dp_max),
            )
    except DPFlowError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # pragma: no cover - defensive UI guard
        st.error(f"Calculation failed: {exc}")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Required Δp [mbar]", f"{result.differential_pressure_mbar:,.2f}")
    m2.metric("Standard volume [Sm³/h]", f"{result.std_volume_flow_sm3_h:,.1f}")
    m3.metric("Pipe velocity [m/s]", f"{result.velocity_m_s:,.3f}")

    _render_warnings(result)
    st.dataframe(pd.DataFrame(_result_rows(result)), width="stretch", hide_index=True)


def render(composition: dict | None) -> None:
    """Render the DP flow meter UI."""
    st.subheader("DP Flow Meter")
    st.caption(
        "Flow rate through Venturi, orifice and V-cone differential-pressure meters (ISO 5167), "
        "with AGA8 (GERG-2008 / DETAIL) supplying the upstream density, isentropic exponent and "
        "standard density. Calculations use "
        "[pvtlib](https://github.com/equinor/pvtlib)."
    )

    if composition is None:
        return

    st.markdown("#### Meter configuration")
    geometry, meter_type = _meter_inputs()
    if geometry is None:
        return

    discharge_coefficient, expansibility = _coefficient_inputs(meter_type)

    st.divider()

    single_tab, multi_tab, sizing_tab = st.tabs(["Single point", "Multi-point", "Sizing (solve Δp)"])
    with single_tab:
        _render_single_point(composition, geometry, discharge_coefficient, expansibility)
    with multi_tab:
        _render_multi_point(composition, geometry, discharge_coefficient, expansibility)
    with sizing_tab:
        _render_sizing(composition, geometry, discharge_coefficient, expansibility)
