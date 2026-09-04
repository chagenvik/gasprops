"""
Shared operating-condition inputs for the Gas Properties module.

Every tab that asks for a single pressure and temperature renders them in the same
order, so the app reads consistently:

    Pressure     [value] [unit]
    Temperature  [value] [unit]
    AGA8 equation

The value comes first with its unit beside it, and the equation of state — a setting
rather than an operating condition — comes last instead of being wedged between the
pressure and the temperature.
"""

from __future__ import annotations

import streamlit as st

PRESSURE_UNITS: tuple[str, ...] = ("bara", "barg", "kPa", "MPa")
TEMPERATURE_UNITS: tuple[str, ...] = ("C", "K")
AGA8_EQUATIONS: tuple[str, ...] = ("GERG-2008", "DETAIL")

AGA8_EQUATION_HELP = "GERG-2008 is recommended for natural gas mixtures."

#: Width ratio between the value input and its unit selector.
_VALUE_UNIT_RATIO = (2, 1)


def temperature_label(unit: str) -> str:
    """Display label for a temperature unit."""
    return "°C" if unit == "C" else "K"


def temperature_floor(unit: str) -> float:
    """Absolute zero expressed in the given temperature unit."""
    return -273.15 if unit == "C" else 0.0


def pressure_input(
    *,
    value_key: str,
    unit_key: str,
    label: str = "Pressure",
    value: float = 100.0,
    min_value: float = 0.0,
    max_value: float = 1000.0,
    step: float = 0.1,
    number_format: str = "%.3f",
    help: str | None = None,
) -> tuple[float, str]:
    """Render ``Pressure [value] [unit]`` on one row and return ``(value, unit)``."""
    value_col, unit_col = st.columns(_VALUE_UNIT_RATIO)
    # The unit is read first so the value input can show it in its label, but it is
    # rendered into the right-hand column so the value still appears first.
    unit = unit_col.selectbox("Pressure unit", list(PRESSURE_UNITS), index=0, key=unit_key)
    amount = value_col.number_input(
        f"{label} [{unit}]",
        min_value=min_value,
        max_value=max_value,
        value=value,
        step=step,
        format=number_format,
        key=value_key,
        help=help,
    )
    return float(amount), str(unit)


def temperature_input(
    *,
    value_key: str,
    unit_key: str,
    label: str = "Temperature",
    value: float = 60.0,
    max_value: float = 2000.0,
    step: float = 0.5,
    number_format: str = "%.2f",
    help: str | None = None,
) -> tuple[float, str, str]:
    """Render ``Temperature [value] [unit]`` on one row.

    Returns ``(value, unit, display_label)`` where the display label is ``°C`` or ``K``.
    """
    value_col, unit_col = st.columns(_VALUE_UNIT_RATIO)
    unit = unit_col.selectbox(
        "Temperature unit",
        list(TEMPERATURE_UNITS),
        index=0,
        key=unit_key,
        format_func=temperature_label,
    )
    display_label = temperature_label(str(unit))
    amount = value_col.number_input(
        f"{label} [{display_label}]",
        min_value=temperature_floor(str(unit)),
        max_value=max_value,
        value=value,
        step=step,
        format=number_format,
        key=value_key,
        help=help,
    )
    return float(amount), str(unit), display_label


def aga8_equation_input(*, key: str, label: str = "AGA8 equation") -> str:
    """Render the AGA8 equation selector, which belongs after the operating conditions."""
    return str(
        st.selectbox(label, list(AGA8_EQUATIONS), index=0, key=key, help=AGA8_EQUATION_HELP)
    )
