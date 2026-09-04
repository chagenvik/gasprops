"""
Flow Converter tab for the Gas Properties module.

Converts between mass flow, actual (line-condition) volume flow and standard volume
flow using AGA8 densities, with configurable standard conditions and time basis.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..flow_converter import (
    FLOW_BASES,
    FLOW_BASIS_LABELS,
    MASS_UNIT_KG,
    STANDARD_CONDITION_PRESETS,
    TIME_UNIT_LABELS,
    TIME_UNIT_SECONDS,
    DPFlowError,
    FlowConversionResult,
    StandardConditions,
    convert_flow,
)

CUSTOM_PRESET = "Custom"

_TIME_UNIT_ORDER = ("s", "h", "d")


def _unit_suffix(time_unit: str) -> str:
    return {"s": "s", "h": "h", "d": "d"}[time_unit]


def _standard_condition_inputs() -> StandardConditions:
    """Render the standard-conditions selector and return the chosen reference state."""
    labels = list(STANDARD_CONDITION_PRESETS.keys()) + [CUSTOM_PRESET]
    preset = st.selectbox(
        "Standard conditions",
        labels,
        index=0,
        key="fc_std_preset",
        help="Reference state the standard volume flow is reported at.",
    )

    if preset == CUSTOM_PRESET:
        c1, c2 = st.columns(2)
        pressure = c1.number_input(
            "Standard pressure [bara]",
            min_value=0.0001, max_value=100.0, value=1.01325, step=0.001, format="%.5f",
            key="fc_std_pressure",
        )
        temperature = c2.number_input(
            "Standard temperature [°C]",
            min_value=-273.14, max_value=200.0, value=15.0, step=0.1, format="%.4f",
            key="fc_std_temperature",
        )
    else:
        pressure, temperature = STANDARD_CONDITION_PRESETS[preset]

    return StandardConditions(pressure_bara=float(pressure), temperature_c=float(temperature))


def _result_table(result: FlowConversionResult, mass_unit: str) -> pd.DataFrame:
    """Full matrix of every quantity on every supported time basis."""
    mass_scale = MASS_UNIT_KG[mass_unit]
    rows: list[dict[str, object]] = []
    for time_unit in _TIME_UNIT_ORDER:
        mass, actual, standard = result.in_time_unit(time_unit)
        suffix = _unit_suffix(time_unit)
        rows.append(
            {
                "Basis": TIME_UNIT_LABELS[time_unit].capitalize(),
                f"Mass flow [{mass_unit}/{suffix}]": mass / mass_scale,
                f"Actual volume flow [m³/{suffix}]": actual,
                f"Standard volume flow [Sm³/{suffix}]": standard,
            }
        )
    return pd.DataFrame(rows)


def _property_rows(result: FlowConversionResult) -> list[dict[str, str]]:
    std = result.standard_conditions
    return [
        {
            "Quantity": f"Actual density ρ ({result.equation})",
            "Value": f"{result.actual_density_kg_m3:.6f}",
            "Unit": "kg/m³",
        },
        {
            "Quantity": f"Standard density ρ_std ({std.label})",
            "Value": f"{result.standard_density_kg_sm3:.6f}",
            "Unit": "kg/Sm³",
        },
        {
            "Quantity": "Volume ratio (actual → standard)",
            "Value": f"{result.formation_volume_ratio:.6f}",
            "Unit": "Sm³/m³",
        },
        {"Quantity": "Pressure", "Value": f"{result.pressure_bara:.5f}", "Unit": "bara"},
        {"Quantity": "Temperature", "Value": f"{result.temperature_c:.4f}", "Unit": "°C"},
    ]


def render(composition: dict | None) -> None:
    """Render the flow converter UI."""
    st.subheader("Flow Converter")
    st.caption(
        "Convert between mass flow, actual (line-condition) volume flow and standard volume flow "
        "using AGA8 (GERG-2008 / DETAIL) densities. Standard conditions default to 1.01325 bara "
        "and 15 °C but can be changed."
    )

    if composition is None:
        return

    st.markdown("#### Known flow rate")
    c1, c2, c3 = st.columns([2, 2, 1])
    basis = c1.selectbox(
        "Convert from",
        list(FLOW_BASES),
        index=0,
        key="fc_basis",
        format_func=lambda b: FLOW_BASIS_LABELS[b],
    )
    value = c2.number_input(
        "Flow rate",
        min_value=0.0, max_value=1e15, value=100000.0, step=100.0, format="%.6f",
        key="fc_value",
    )
    time_unit = c3.selectbox(
        "Time basis",
        list(TIME_UNIT_SECONDS.keys()),
        index=1,
        key="fc_time_unit",
        format_func=lambda u: TIME_UNIT_LABELS[u].capitalize(),
    )

    mass_unit = "kg"
    if basis == "mass":
        mass_unit = st.radio(
            "Mass unit",
            list(MASS_UNIT_KG.keys()),
            index=0,
            key="fc_mass_unit",
            horizontal=True,
            format_func=lambda u: "kilogram (kg)" if u == "kg" else "tonne (t)",
        )

    unit_hint = {
        "mass": f"{mass_unit}/{_unit_suffix(time_unit)}",
        "actual_volume": f"m³/{_unit_suffix(time_unit)}",
        "standard_volume": f"Sm³/{_unit_suffix(time_unit)}",
    }[basis]
    st.caption(f"Input is interpreted as **{value:,.6g} {unit_hint}**.")

    st.markdown("#### Actual (line) conditions")
    c4, c5, c6 = st.columns(3)
    equation = c4.selectbox(
        "AGA8 equation", ["GERG-2008", "DETAIL"], index=0, key="fc_eos",
        help="GERG-2008 is recommended for natural gas mixtures.",
    )
    pressure_unit = c5.selectbox(
        "Pressure unit", ["bara", "barg", "kPa", "MPa"], index=0, key="fc_p_unit"
    )
    temperature_unit = c6.selectbox(
        "Temperature unit", ["C", "K"], index=0, key="fc_t_unit",
        format_func=lambda x: "°C" if x == "C" else "K",
    )

    c7, c8 = st.columns(2)
    pressure = c7.number_input(
        f"Pressure [{pressure_unit}]",
        min_value=0.0, max_value=1000.0, value=60.0, step=0.1, format="%.4f",
        key="fc_pressure",
    )
    temperature = c8.number_input(
        f"Temperature [{'°C' if temperature_unit == 'C' else 'K'}]",
        min_value=-273.15 if temperature_unit == "C" else 0.0,
        max_value=2000.0, value=20.0, step=0.5, format="%.3f",
        key="fc_temperature",
    )

    st.markdown("#### Standard conditions")
    standard_conditions = _standard_condition_inputs()

    if not st.button("Convert", type="primary", key="fc_convert"):
        return

    try:
        result = convert_flow(
            composition,
            float(value),
            basis,
            float(pressure),
            float(temperature),
            time_unit=time_unit,
            mass_unit=mass_unit,
            pressure_unit=pressure_unit,
            temperature_unit=temperature_unit,
            equation=equation,
            standard_conditions=standard_conditions,
        )
    except DPFlowError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # pragma: no cover - defensive UI guard
        st.error(f"Conversion failed: {exc}")
        return

    mass, actual, standard = result.in_time_unit(time_unit)
    suffix = _unit_suffix(time_unit)
    m1, m2, m3 = st.columns(3)
    m1.metric(
        f"Mass flow [{mass_unit}/{suffix}]",
        f"{mass / MASS_UNIT_KG[mass_unit]:,.4f}",
    )
    m2.metric(f"Actual volume flow [m³/{suffix}]", f"{actual:,.4f}")
    m3.metric(f"Standard volume flow [Sm³/{suffix}]", f"{standard:,.4f}")

    st.markdown("##### All time bases")
    table = _result_table(result, mass_unit)
    st.dataframe(
        table.style.format({col: "{:,.6g}" for col in table.columns if col != "Basis"}),
        width="stretch",
        hide_index=True,
    )

    st.markdown("##### Densities used")
    st.dataframe(pd.DataFrame(_property_rows(result)), width="stretch", hide_index=True)

    st.download_button(
        "Download results (CSV)",
        data=table.to_csv(index=False).encode(),
        file_name=f"flow_conversion_{pressure:.4g}{pressure_unit}_{temperature:.4g}{temperature_unit}.csv",
        mime="text/csv",
        key="fc_dl",
    )
