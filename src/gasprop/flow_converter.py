"""
Flow rate conversion for the Gas Properties module.

Converts between mass flow, actual (line-condition) volume flow and standard volume
flow using AGA8 (GERG-2008 / DETAIL) densities from ``pvtlib``:

    actual volume flow = mass flow / rho(P, T)
    standard volume flow = mass flow / rho(P_std, T_std)

Standard conditions default to 1.01325 bara and 15 degC (ISO 13443 / Sm3) but are
fully configurable, so normal conditions (0 degC, Nm3) or US standard conditions
(60 degF) can be used instead.

This module is deliberately free of Streamlit so it can be unit tested directly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .dp_flow import DPFlowError, _normalised_mol_percent, _to_bara, _to_celsius, _aga8

FlowBasis = Literal["mass", "actual_volume", "standard_volume"]

#: Supported conversion bases, in the order they are presented to the user.
FLOW_BASES: tuple[FlowBasis, ...] = ("mass", "actual_volume", "standard_volume")

FLOW_BASIS_LABELS: dict[FlowBasis, str] = {
    "mass": "Mass flow",
    "actual_volume": "Actual volume flow",
    "standard_volume": "Standard volume flow",
}

#: Seconds per time unit. Values are exact.
TIME_UNIT_SECONDS: dict[str, float] = {
    "s": 1.0,
    "h": 3600.0,
    "d": 86400.0,
}

TIME_UNIT_LABELS: dict[str, str] = {
    "s": "per second",
    "h": "per hour",
    "d": "per day",
}

#: Mass units expressed in kilograms.
MASS_UNIT_KG: dict[str, float] = {
    "kg": 1.0,
    "t": 1000.0,
}

#: Named standard-condition presets. Pressure in bara, temperature in degC.
STANDARD_CONDITION_PRESETS: dict[str, tuple[float, float]] = {
    "ISO 13443 — Sm³ (1.01325 bara, 15 °C)": (1.01325, 15.0),
    "Normal — Nm³ (1.01325 bara, 0 °C)": (1.01325, 0.0),
    "US standard (1.01325 bara, 60 °F)": (1.01325, 15.555555555555555),
    "Metric standard (1.0 bara, 15 °C)": (1.0, 15.0),
}

DEFAULT_STANDARD_PRESSURE_BARA, DEFAULT_STANDARD_TEMPERATURE_C = STANDARD_CONDITION_PRESETS[
    "ISO 13443 — Sm³ (1.01325 bara, 15 °C)"
]


@dataclass(frozen=True)
class StandardConditions:
    """Reference conditions used for the standard volume flow."""

    pressure_bara: float = DEFAULT_STANDARD_PRESSURE_BARA
    temperature_c: float = DEFAULT_STANDARD_TEMPERATURE_C

    def __post_init__(self) -> None:
        if not math.isfinite(self.pressure_bara) or self.pressure_bara <= 0.0:
            raise DPFlowError("Standard pressure must be a finite number greater than zero.")
        if not math.isfinite(self.temperature_c) or self.temperature_c <= -273.15:
            raise DPFlowError("Standard temperature must be finite and above absolute zero.")

    @property
    def label(self) -> str:
        return f"{self.pressure_bara:.5g} bara, {self.temperature_c:.4g} °C"


@dataclass(frozen=True)
class FlowConversionResult:
    """Equivalent flow rates for one stream, all on a per-second basis.

    The per-second values are the canonical result; :meth:`in_time_unit` scales them
    to the time basis the caller wants to display.
    """

    mass_flow_kg_s: float
    actual_volume_flow_m3_s: float
    standard_volume_flow_sm3_s: float
    actual_density_kg_m3: float
    standard_density_kg_sm3: float
    pressure_bara: float
    temperature_c: float
    standard_conditions: StandardConditions
    equation: str

    def in_time_unit(self, time_unit: str) -> tuple[float, float, float]:
        """Return (mass, actual volume, standard volume) flow per the given time unit."""
        factor = _time_unit_seconds(time_unit)
        return (
            self.mass_flow_kg_s * factor,
            self.actual_volume_flow_m3_s * factor,
            self.standard_volume_flow_sm3_s * factor,
        )

    @property
    def formation_volume_ratio(self) -> float:
        """Standard volume per unit actual volume, i.e. rho(P,T) / rho_std [Sm3/m3]."""
        return self.actual_density_kg_m3 / self.standard_density_kg_sm3


def _time_unit_seconds(time_unit: str) -> float:
    try:
        return TIME_UNIT_SECONDS[time_unit]
    except KeyError:
        raise DPFlowError(
            f"Unsupported time unit '{time_unit}'. Expected one of {sorted(TIME_UNIT_SECONDS)}."
        ) from None


def _mass_unit_kg(mass_unit: str) -> float:
    try:
        return MASS_UNIT_KG[mass_unit]
    except KeyError:
        raise DPFlowError(
            f"Unsupported mass unit '{mass_unit}'. Expected one of {sorted(MASS_UNIT_KG)}."
        ) from None


def _density(
    composition: dict[str, float],
    pressure_bara: float,
    temperature_c: float,
    equation: str,
    what: str,
) -> float:
    """AGA8 mass density [kg/m3], with native failures wrapped in DPFlowError."""
    try:
        result = _aga8(equation).calculate_from_PT(
            composition=composition,
            pressure=pressure_bara,
            temperature=temperature_c,
            pressure_unit="bara",
            temperature_unit="C",
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        raise DPFlowError(f"AGA8 {what} calculation failed: {exc}") from exc

    density = float(result["rho"])
    if not math.isfinite(density) or density <= 0.0:
        raise DPFlowError(
            f"AGA8 did not return a valid {what}. Check that the point is inside the AGA8 range of use."
        )
    return density


def convert_flow(
    composition: dict[str, float],
    value: float,
    basis: FlowBasis,
    pressure: float,
    temperature: float,
    *,
    time_unit: str = "h",
    mass_unit: str = "kg",
    pressure_unit: str = "bara",
    temperature_unit: str = "C",
    equation: str = "GERG-2008",
    standard_conditions: StandardConditions | None = None,
) -> FlowConversionResult:
    """Convert one flow rate into its mass, actual-volume and standard-volume equivalents.

    Parameters
    ----------
    composition:
        Gas composition in mol% (normalised internally).
    value:
        The known flow rate, expressed in ``basis`` per ``time_unit``. Mass flow uses
        ``mass_unit``; volume flows use m3 and Sm3 respectively.
    basis:
        Which quantity ``value`` represents.
    pressure, temperature:
        Actual (line) conditions, in ``pressure_unit`` and ``temperature_unit``.
    standard_conditions:
        Reference conditions for the standard volume flow. Defaults to 1.01325 bara / 15 degC.
    """
    if basis not in FLOW_BASES:
        raise DPFlowError(f"Unknown flow basis '{basis}'. Expected one of {list(FLOW_BASES)}.")

    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise DPFlowError("Flow rate must be a finite number.") from exc
    if not math.isfinite(value) or value < 0.0:
        raise DPFlowError("Flow rate must be a finite number greater than or equal to zero.")

    seconds = _time_unit_seconds(time_unit)
    mass_factor = _mass_unit_kg(mass_unit)
    std = standard_conditions if standard_conditions is not None else StandardConditions()

    pressure_bara = _to_bara(pressure, pressure_unit)
    temperature_c = _to_celsius(temperature, temperature_unit)
    if not math.isfinite(pressure_bara) or pressure_bara <= 0.0:
        raise DPFlowError("Pressure must be a finite number greater than zero.")
    if not math.isfinite(temperature_c) or temperature_c <= -273.15:
        raise DPFlowError("Temperature must be finite and above absolute zero.")

    normalised = _normalised_mol_percent(composition)
    actual_density = _density(normalised, pressure_bara, temperature_c, equation, "density")
    standard_density = _density(
        normalised, std.pressure_bara, std.temperature_c, equation, "standard density"
    )

    # Everything is routed through mass flow, which is the only conditions-independent quantity.
    if basis == "mass":
        mass_flow_kg_s = value * mass_factor / seconds
    elif basis == "actual_volume":
        mass_flow_kg_s = value / seconds * actual_density
    else:
        mass_flow_kg_s = value / seconds * standard_density

    return FlowConversionResult(
        mass_flow_kg_s=mass_flow_kg_s,
        actual_volume_flow_m3_s=mass_flow_kg_s / actual_density,
        standard_volume_flow_sm3_s=mass_flow_kg_s / standard_density,
        actual_density_kg_m3=actual_density,
        standard_density_kg_sm3=standard_density,
        pressure_bara=pressure_bara,
        temperature_c=temperature_c,
        standard_conditions=std,
        equation=equation,
    )
