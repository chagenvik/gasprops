"""
Flow Converter tab for the Gas Properties module.

Converts between mass flow, actual (line-condition) volume flow and standard volume
flow using AGA8 densities, with configurable standard conditions and time basis.
"""

from __future__ import annotations

import math

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
from ..operating_conditions import (
    aga8_equation_input,
    pressure_input,
    temperature_input,
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


def _format_number(value: float) -> str:
    """Format an engineering quantity with a readable, magnitude-dependent precision.

    Flow rates in this tab span many orders of magnitude (m³/s up to Sm³/d), so a fixed
    number of decimals is either noise or a loss of resolution. Roughly six significant
    digits are kept without printing meaningless trailing decimals on large numbers.
    """
    if value is None or not math.isfinite(value):
        return "–"
    magnitude = abs(value)
    if magnitude == 0.0:
        return "0"
    if magnitude >= 100_000.0:
        return f"{value:,.0f}"
    if magnitude >= 1_000.0:
        return f"{value:,.1f}"
    if magnitude >= 1.0:
        return f"{value:,.3f}"
    if magnitude >= 0.001:
        return f"{value:.5f}"
    return f"{value:.4e}"


def _result_frame(result: FlowConversionResult, mass_unit: str) -> pd.DataFrame:
    """Quantities as rows and time bases as columns.

    The time basis lives in the column header rather than in each cell's unit, so every
    column holds the same quantity and the frame has no gaps. Reading a cell as
    "<row label> <column label>" gives the full unit, e.g. "Mass flow [kg]" + "Per hour".
    """
    mass_scale = MASS_UNIT_KG[mass_unit]
    columns: dict[str, list[float]] = {}
    for time_unit in _TIME_UNIT_ORDER:
        mass, actual, standard = result.in_time_unit(time_unit)
        columns[TIME_UNIT_LABELS[time_unit].capitalize()] = [
            mass / mass_scale,
            actual,
            standard,
        ]
    index = [
        f"Mass flow [{mass_unit}]",
        "Actual volume flow [m³]",
        "Standard volume flow [Sm³]",
    ]
    return pd.DataFrame(columns, index=index)


def _property_rows(result: FlowConversionResult) -> list[dict[str, str]]:
    std = result.standard_conditions
    return [
        {
            "Quantity": f"Actual density ρ ({result.equation})",
            "Value": f"{result.actual_density_kg_m3:,.4f}",
            "Unit": "kg/m³",
        },
        {
            "Quantity": f"Standard density ρ_std ({std.label})",
            "Value": f"{result.standard_density_kg_sm3:,.5f}",
            "Unit": "kg/Sm³",
        },
        {
            "Quantity": "Volume ratio (actual → standard)",
            "Value": f"{result.formation_volume_ratio:,.3f}",
            "Unit": "Sm³/m³",
        },
        {"Quantity": "Pressure", "Value": f"{result.pressure_bara:,.3f}", "Unit": "bara"},
        {"Quantity": "Temperature", "Value": f"{result.temperature_c:,.2f}", "Unit": "°C"},
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
        min_value=0.0, max_value=1e15, value=100000.0, step=100.0, format="%.2f",
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
    st.caption(f"Input is interpreted as **{_format_number(float(value))} {unit_hint}**.")

    st.markdown("#### Actual (line) conditions")
    pressure, pressure_unit = pressure_input(
        value_key="fc_pressure", unit_key="fc_p_unit", value=60.0,
    )
    temperature, temperature_unit, _ = temperature_input(
        value_key="fc_temperature", unit_key="fc_t_unit", value=20.0,
    )
    equation = aga8_equation_input(key="fc_eos")

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
        _format_number(mass / MASS_UNIT_KG[mass_unit]),
    )
    m2.metric(f"Actual volume flow [m³/{suffix}]", _format_number(actual))
    m3.metric(f"Standard volume flow [Sm³/{suffix}]", _format_number(standard))

    st.markdown("##### All time bases")
    frame = _result_frame(result, mass_unit)
    display = frame.map(_format_number).reset_index(names="Quantity")
    st.dataframe(display, width="stretch", hide_index=True)

    st.markdown("##### Densities used")
    st.dataframe(pd.DataFrame(_property_rows(result)), width="stretch", hide_index=True)

    st.download_button(
        "Download results (CSV)",
        # The CSV keeps full precision; only the on-screen table is rounded for readability.
        data=frame.to_csv(index_label="Quantity").encode(),
        file_name=f"flow_conversion_{pressure:.4g}{pressure_unit}_{temperature:.4g}{temperature_unit}.csv",
        mime="text/csv",
        key="fc_dl",
    )
