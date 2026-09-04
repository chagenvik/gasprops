"""
Differential-pressure (DP) flow meter calculations for the Gas Properties module.

The module combines AGA8 (GERG-2008 / DETAIL) gas properties from ``pvtlib`` with
the ISO 5167 DP-meter models in ``pvtlib.metering.differential_pressure_flowmeters``:

    * Venturi tube   -- ISO 5167-4:2022
    * Orifice plate  -- ISO 5167-2:2022 (Reader-Harris/Gallagher discharge coefficient)
    * V-cone meter   -- ISO 5167-5:2022 (Stewart expansibility)

AGA8 supplies the upstream density, isentropic exponent (used for expansibility) and
the standard density used to convert mass flow to standard volume flow. AGA8 does not
provide viscosity, so the dynamic viscosity needed for the orifice Reynolds number is
either supplied by the caller or calculated with NeqSim.

This module is deliberately free of Streamlit so it can be unit tested directly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

import pvtlib
from pvtlib.metering import differential_pressure_flowmeters as dpm

from .domain import COMPONENTS, NEQSIM_NAMES

MeterType = Literal["Venturi", "Orifice", "V-cone"]

METER_TYPES: tuple[MeterType, ...] = ("Venturi", "Orifice", "V-cone")

#: Tapping types supported by the ISO 5167-2 Reader-Harris/Gallagher equation.
ORIFICE_TAPPINGS: tuple[str, ...] = ("corner", "flange", "D", "D/2")

#: Reference conditions for standard volume flow (Sm3): 1.01325 bara and 15 degC.
STANDARD_PRESSURE_BARA = 1.01325
STANDARD_TEMPERATURE_C = 15.0

#: ISO 5167-4:2022 default discharge coefficient for an "as cast" Venturi tube.
DEFAULT_C_VENTURI = 0.984
#: ISO 5167-5:2022 default discharge coefficient for an uncalibrated cone meter.
DEFAULT_C_V_CONE = 0.82

#: Discharge-coefficient presets offered for Venturi tubes (ISO 5167-4:2022, table 1).
VENTURI_C_PRESETS: dict[str, float] = {
    "As cast convergent (0.984)": 0.984,
    "Machined convergent (0.995)": 0.995,
    "Rough-welded sheet-iron convergent (0.985)": 0.985,
}

#: Range-of-use limits used for the ISO 5167 sanity checks. The Venturi values
#: are for an as-cast convergent; other constructions have different limits.
ISO_LIMITS: dict[str, dict[str, tuple[float, float]]] = {
    "Venturi": {
        "pipe_diameter_mm": (100.0, 800.0),
        "beta": (0.30, 0.75),
        "reynolds": (2.0e5, 2.0e6),
    },
    "Orifice": {
        "pipe_diameter_mm": (50.0, 1000.0),
        "beta": (0.10, 0.75),
        "reynolds": (5.0e3, math.inf),
    },
    "V-cone": {
        "pipe_diameter_mm": (50.0, 500.0),
        "beta": (0.45, 0.75),
        "reynolds": (8.0e4, 1.2e7),
    },
}

#: Lowest pressure ratio p2/p1 for which the expansibility correlations are valid.
MIN_PRESSURE_RATIO = 0.75


class DPFlowError(ValueError):
    """Raised when the DP meter input is not physically valid."""


# ── Geometry ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MeterGeometry:
    """Geometry of a DP flow meter.

    Parameters
    ----------
    meter_type:
        ``"Venturi"``, ``"Orifice"`` or ``"V-cone"``.
    pipe_diameter_mm:
        Internal pipe diameter at the upstream tapping, ``D`` [mm].
    bore_diameter_mm:
        For Venturi and orifice meters this is the throat/bore diameter ``d`` [mm].
        For a V-cone meter it is the cone diameter ``dc`` at the beta edge [mm].
    tapping:
        Orifice tapping type; ignored for the other meter types.
    """

    meter_type: MeterType
    pipe_diameter_mm: float
    bore_diameter_mm: float
    tapping: str = "corner"

    def __post_init__(self) -> None:
        if self.meter_type not in METER_TYPES:
            raise DPFlowError(f"Unknown meter type '{self.meter_type}'. Expected one of {list(METER_TYPES)}.")
        if not math.isfinite(self.pipe_diameter_mm) or self.pipe_diameter_mm <= 0.0:
            raise DPFlowError("Pipe diameter D must be a finite number greater than zero.")
        if not math.isfinite(self.bore_diameter_mm) or self.bore_diameter_mm <= 0.0:
            raise DPFlowError("Bore/cone diameter must be a finite number greater than zero.")
        if self.bore_diameter_mm >= self.pipe_diameter_mm:
            raise DPFlowError("Bore/cone diameter must be smaller than the pipe diameter D.")
        if self.meter_type == "Orifice" and self.tapping not in ORIFICE_TAPPINGS:
            raise DPFlowError(
                f"Unknown orifice tapping '{self.tapping}'. Expected one of {list(ORIFICE_TAPPINGS)}."
            )

    @property
    def D_m(self) -> float:
        """Pipe diameter [m]."""
        return self.pipe_diameter_mm / 1000.0

    @property
    def bore_m(self) -> float:
        """Throat/bore diameter (Venturi, orifice) or cone diameter (V-cone) [m]."""
        return self.bore_diameter_mm / 1000.0

    @property
    def beta(self) -> float:
        """Diameter ratio of the meter [-]."""
        if self.meter_type == "V-cone":
            return float(dpm.calculate_beta_V_cone(D=self.D_m, dc=self.bore_m))
        return float(dpm.calculate_beta_DP_meter(D=self.D_m, d=self.bore_m))

    @property
    def throat_diameter_m(self) -> float:
        """Equivalent throat diameter ``beta * D`` [m], used for the V-cone."""
        return self.beta * self.D_m


# ── Gas state ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class GasState:
    """AGA8 gas properties at the upstream tapping plus the standard density."""

    equation: str
    pressure_bara: float
    temperature_c: float
    density_kg_m3: float
    kappa: float
    z: float
    molar_mass_g_mol: float
    speed_of_sound_m_s: float
    standard_density_kg_sm3: float
    viscosity_pa_s: float | None
    viscosity_source: str


def _normalised_mol_percent(composition: dict[str, float]) -> dict[str, float]:
    positive: dict[str, float] = {}
    for name, raw_value in composition.items():
        if name not in COMPONENTS:
            raise DPFlowError(
                f"Unknown gas component '{name}'. Expected an AGA8 component."
            )
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise DPFlowError(
                f"Composition value for {name} must be a finite number."
            ) from exc
        if not math.isfinite(value):
            raise DPFlowError(f"Composition value for {name} must be finite.")
        if value < 0.0:
            raise DPFlowError(f"Composition value for {name} must not be negative.")
        if value > 0.0:
            positive[name] = value
    total = sum(positive.values())
    if total <= 0.0:
        raise DPFlowError("Composition total must be greater than zero.")
    return {k: v / total * 100.0 for k, v in positive.items()}


def _aga8(equation: str) -> pvtlib.AGA8:
    # pvtlib.AGA8 owns a mutable native adapter, so instances must not be shared
    # between concurrent Streamlit sessions.
    return pvtlib.AGA8(equation)


def _to_bara(pressure: float, pressure_unit: str) -> float:
    """Convert a pressure to bara for the ISO 5167 expansibility correlations."""
    unit = pressure_unit.strip()
    if unit == "bara":
        return float(pressure)
    if unit == "barg":
        return float(pressure) + STANDARD_PRESSURE_BARA
    if unit == "kPa":
        return float(pressure) / 100.0
    if unit == "MPa":
        return float(pressure) * 10.0
    raise DPFlowError(f"Unsupported pressure unit '{pressure_unit}'.")


def _to_celsius(temperature: float, temperature_unit: str) -> float:
    unit = temperature_unit.strip()
    if unit == "C":
        return float(temperature)
    if unit == "K":
        return float(temperature) - 273.15
    raise DPFlowError(f"Unsupported temperature unit '{temperature_unit}'.")


def standard_density(composition: dict[str, float], equation: str = "GERG-2008") -> float:
    """Return the AGA8 density at 1.01325 bara and 15 degC [kg/Sm3]."""
    try:
        result = _aga8(equation).calculate_from_PT(
            composition=_normalised_mol_percent(composition),
            pressure=STANDARD_PRESSURE_BARA,
            temperature=STANDARD_TEMPERATURE_C,
            pressure_unit="bara",
            temperature_unit="C",
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        raise DPFlowError(f"AGA8 standard-density calculation failed: {exc}") from exc
    density = float(result["rho"])
    if not math.isfinite(density) or density <= 0.0:
        raise DPFlowError("AGA8 did not return a valid standard density.")
    return density


def viscosity_from_neqsim(
    composition: dict[str, float],
    pressure_bara: float,
    temperature_c: float,
) -> float | None:
    """Return the gas-phase dynamic viscosity [Pa*s] from NeqSim, or ``None`` on failure.

    AGA8 does not model viscosity, so NeqSim (SRK) is used as the transport-property
    source. Returns ``None`` if NeqSim is unavailable or the flash does not produce a
    gas phase, so the caller can fall back to a user-supplied viscosity.
    """
    try:
        composition_key = tuple(sorted(_normalised_mol_percent(composition).items()))
    except DPFlowError:
        return None
    return _viscosity_from_neqsim_cached(composition_key, float(pressure_bara), float(temperature_c))


@lru_cache(maxsize=256)
def _viscosity_from_neqsim_cached(
    composition_key: tuple[tuple[str, float], ...],
    pressure_bara: float,
    temperature_c: float,
) -> float | None:
    try:
        from neqsim.thermo import TPflash, fluid

        gas_fluid = fluid("srk")
        for name, mol_percent in composition_key:
            neqsim_name = NEQSIM_NAMES.get(name)
            if neqsim_name is None:
                continue
            gas_fluid.addComponent(neqsim_name, float(mol_percent))
        gas_fluid.setMixingRule(2)
        gas_fluid.setTemperature(float(temperature_c), "C")
        gas_fluid.setPressure(float(pressure_bara), "bara")
        TPflash(gas_fluid)
        gas_fluid.initProperties()

        for index in range(int(gas_fluid.getNumberOfPhases())):
            phase = gas_fluid.getPhase(index)
            if "gas" not in str(phase.getPhaseTypeName()).lower():
                continue
            viscosity = float(phase.getPhysicalProperties().getViscosity())
            if math.isfinite(viscosity) and viscosity > 0.0:
                return viscosity
        return None
    except Exception:
        return None


def calculate_gas_state(
    composition: dict[str, float],
    pressure: float,
    temperature: float,
    *,
    pressure_unit: str = "bara",
    temperature_unit: str = "C",
    equation: str = "GERG-2008",
    viscosity_pa_s: float | None = None,
) -> GasState:
    """Calculate the AGA8 gas state at the upstream tapping of a DP meter.

    ``viscosity_pa_s`` overrides the NeqSim viscosity when given.
    """
    pressure_bara = _to_bara(pressure, pressure_unit)
    temperature_c = _to_celsius(temperature, temperature_unit)

    if not math.isfinite(pressure_bara) or pressure_bara <= 0.0:
        raise DPFlowError("Upstream pressure must be a finite number greater than zero.")
    if not math.isfinite(temperature_c) or temperature_c <= -273.15:
        raise DPFlowError("Temperature must be finite and greater than absolute zero.")

    normalised = _normalised_mol_percent(composition)
    try:
        result = _aga8(equation).calculate_from_PT(
            composition=normalised,
            pressure=pressure_bara,
            temperature=temperature_c,
            pressure_unit="bara",
            temperature_unit="C",
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        raise DPFlowError(f"AGA8 gas-state calculation failed: {exc}") from exc

    density = float(result["rho"])
    if not math.isfinite(density) or density <= 0.0:
        raise DPFlowError(
            "AGA8 did not return a valid density for the given composition and P/T. "
            "Check that the point is inside the AGA8 range of use."
        )

    if viscosity_pa_s is not None:
        if not math.isfinite(float(viscosity_pa_s)) or float(viscosity_pa_s) <= 0.0:
            raise DPFlowError("Dynamic viscosity must be a finite number greater than zero.")
        viscosity: float | None = float(viscosity_pa_s)
        viscosity_source = "Manual"
    else:
        viscosity = viscosity_from_neqsim(normalised, pressure_bara, temperature_c)
        viscosity_source = "NeqSim (SRK)" if viscosity is not None else "Unavailable"

    return GasState(
        equation=equation,
        pressure_bara=pressure_bara,
        temperature_c=temperature_c,
        density_kg_m3=density,
        kappa=float(result["kappa"]),
        z=float(result["z"]),
        molar_mass_g_mol=float(result["mm"]),
        speed_of_sound_m_s=float(result["w"]),
        standard_density_kg_sm3=standard_density(normalised, equation),
        viscosity_pa_s=viscosity,
        viscosity_source=viscosity_source,
    )


# ── Expansibility ─────────────────────────────────────────────────────────────
#: Relative pressure drop dP/p1 below which the expansibility is taken as exactly 1.
#: The ISO 5167-4 Venturi formula contains the factor (1 - tau^((k-1)/k)) / (1 - tau),
#: which suffers catastrophic cancellation as tau -> 1: it returns values slightly above
#: 1 and eventually divides by zero. Below this threshold the true value of 1 - epsilon
#: is under 1e-9, so the exact limit is returned instead.
NEGLIGIBLE_PRESSURE_DROP_RATIO = 1.0e-9


def calculate_expansibility(
    geometry: MeterGeometry,
    pressure_bara: float,
    dp_mbar: float,
    kappa: float,
) -> float:
    """Expansibility factor for the given meter type [-]."""
    if pressure_bara <= 0.0:
        raise DPFlowError("Upstream pressure must be greater than zero.")

    # All three correlations tend to 1 as the pressure drop vanishes.
    if dp_mbar / (1000.0 * pressure_bara) < NEGLIGIBLE_PRESSURE_DROP_RATIO:
        return 1.0

    beta = geometry.beta
    if geometry.meter_type == "Venturi":
        return float(dpm.calculate_expansibility_venturi(P1=pressure_bara, dP=dp_mbar, beta=beta, kappa=kappa))
    if geometry.meter_type == "Orifice":
        return float(dpm.calculate_expansibility_orifice(P1=pressure_bara, dP=dp_mbar, beta=beta, kappa=kappa))
    return float(
        dpm.calculate_expansibility_Stewart_V_cone(beta=beta, P1=pressure_bara, dP=dp_mbar, k=kappa)
    )


def reynolds_number(density_kg_m3: float, velocity_m_s: float, diameter_m: float, viscosity_pa_s: float) -> float:
    """Pipe Reynolds number ``rho * v * D / mu`` [-]."""
    if viscosity_pa_s <= 0.0:
        raise DPFlowError("Dynamic viscosity must be greater than zero.")
    return density_kg_m3 * velocity_m_s * diameter_m / viscosity_pa_s


# ── Flow calculation ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DPFlowResult:
    """Result of a DP meter flow calculation."""

    meter_type: MeterType
    beta: float
    discharge_coefficient: float
    discharge_coefficient_source: str
    expansibility: float
    expansibility_source: str
    reynolds_number: float | None
    mass_flow_kg_h: float
    volume_flow_m3_h: float
    std_volume_flow_sm3_h: float
    std_volume_flow_sm3_d: float
    velocity_m_s: float
    differential_pressure_mbar: float
    pressure_ratio: float
    gas_state: GasState
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _range_warnings(
    geometry: MeterGeometry,
    re_number: float | None,
    pressure_ratio: float,
) -> list[str]:
    """Collect ISO 5167 range-of-use warnings. An empty list means no warnings."""
    warnings: list[str] = []
    limits = ISO_LIMITS[geometry.meter_type]

    d_min, d_max = limits["pipe_diameter_mm"]
    if not (d_min <= geometry.pipe_diameter_mm <= d_max):
        warnings.append(
            f"Pipe diameter D = {geometry.pipe_diameter_mm:.1f} mm is outside the "
            f"ISO 5167 range of use ({d_min:.0f}-{d_max:.0f} mm) for a {geometry.meter_type} meter."
        )

    beta = geometry.beta
    beta_min, beta_max = limits["beta"]
    if not (beta_min <= beta <= beta_max):
        warnings.append(
            f"Beta = {beta:.4f} is outside the ISO 5167 range of use "
            f"({beta_min:.2f}-{beta_max:.2f}) for a {geometry.meter_type} meter."
        )

    if geometry.meter_type == "Orifice" and geometry.bore_diameter_mm < 12.5:
        warnings.append(
            f"Orifice bore d = {geometry.bore_diameter_mm:.2f} mm is below the ISO 5167-2 minimum of 12.5 mm."
        )

    if re_number is None or not math.isfinite(re_number):
        warnings.append(
            "Reynolds number could not be checked because dynamic viscosity is unavailable."
        )
    else:
        if geometry.meter_type == "Orifice" and beta > 0.56:
            re_min, re_max = 16000.0 * beta**2, math.inf
        else:
            re_min, re_max = limits["reynolds"]
        if re_number < re_min:
            warnings.append(
                f"Reynolds number {re_number:.3e} is below the ISO 5167 minimum "
                f"of {re_min:.1e} for a {geometry.meter_type} meter."
            )
        elif re_number > re_max:
            warnings.append(
                f"Reynolds number {re_number:.3e} is above the ISO 5167 maximum "
                f"of {re_max:.1e} for a {geometry.meter_type} meter."
            )

    if pressure_ratio < MIN_PRESSURE_RATIO:
        warnings.append(
            f"Pressure ratio p2/p1 = {pressure_ratio:.4f} is below {MIN_PRESSURE_RATIO:.2f}; "
            "the expansibility correlation is outside its validated range."
        )

    return warnings


def calculate_dp_flow(
    geometry: MeterGeometry,
    gas_state: GasState,
    dp_mbar: float,
    *,
    discharge_coefficient: float | None = None,
    expansibility: float | None = None,
) -> DPFlowResult:
    """Calculate the flow rate through a DP meter from an AGA8 gas state.

    Parameters
    ----------
    geometry:
        Meter geometry.
    gas_state:
        Upstream gas state, normally from :func:`calculate_gas_state`.
    dp_mbar:
        Differential pressure across the meter [mbar].
    discharge_coefficient:
        Fixed discharge coefficient. When ``None`` the ISO 5167 default is used for
        Venturi and V-cone meters, and the Reader-Harris/Gallagher equation is solved
        iteratively for orifice plates (which requires a viscosity).
    expansibility:
        Fixed expansibility factor. When ``None`` it is calculated from the AGA8
        isentropic exponent using the correlation for the given meter type.
    """
    dp_mbar = float(dp_mbar)
    if not math.isfinite(dp_mbar) or dp_mbar < 0.0:
        raise DPFlowError("Differential pressure must be a finite number greater than or equal to zero.")

    p1 = gas_state.pressure_bara
    if not math.isfinite(p1) or p1 <= 0.0:
        raise DPFlowError("Upstream pressure must be a finite number greater than zero.")
    p2 = p1 - dp_mbar / 1000.0
    if p2 <= 0.0:
        raise DPFlowError(
            f"Differential pressure ({dp_mbar:.1f} mbar) is larger than the upstream pressure "
            f"({p1:.4f} bara). Check the inputs."
        )
    pressure_ratio = p2 / p1

    if expansibility is None:
        if not math.isfinite(gas_state.kappa) or gas_state.kappa <= 0.0:
            raise DPFlowError(
                "Isentropic exponent must be a finite number greater than zero."
            )
        epsilon = calculate_expansibility(geometry, p1, dp_mbar, gas_state.kappa)
        epsilon_source = "Calculated from AGA8 kappa"
    else:
        epsilon = float(expansibility)
        epsilon_source = "Manual"
    if not math.isfinite(epsilon) or not (0.0 < epsilon <= 1.0):
        raise DPFlowError(
            "Expansibility factor must be a finite number greater than zero and at most one."
        )

    rho1 = gas_state.density_kg_m3
    if not math.isfinite(rho1) or rho1 <= 0.0:
        raise DPFlowError("Upstream density must be a finite number greater than zero.")
    if (
        not math.isfinite(gas_state.standard_density_kg_sm3)
        or gas_state.standard_density_kg_sm3 <= 0.0
    ):
        raise DPFlowError("Standard density must be a finite number greater than zero.")

    if discharge_coefficient is None:
        fixed_c = None
    else:
        try:
            fixed_c = float(discharge_coefficient)
        except (TypeError, ValueError) as exc:
            raise DPFlowError(
                "Discharge coefficient must be a finite number greater than zero."
            ) from exc
        if not math.isfinite(fixed_c) or fixed_c <= 0.0:
            raise DPFlowError(
                "Discharge coefficient must be a finite number greater than zero."
            )

    # pvtlib rejects dP = 0 for Venturi tubes when its own input checks are enabled, but a
    # zero differential pressure is a valid no-flow point. Our own validation above already
    # covers the invalid cases, so the pvtlib checks are only enabled for dP > 0.
    check_input = dp_mbar > 0.0

    if geometry.meter_type == "Venturi":
        c_used = DEFAULT_C_VENTURI if fixed_c is None else fixed_c
        c_source = "ISO 5167-4 default (as cast)" if fixed_c is None else "Manual"
        flow = dpm.calculate_flow_venturi(
            D=geometry.D_m,
            d=geometry.bore_m,
            dP=dp_mbar,
            rho1=rho1,
            C=c_used,
            epsilon=epsilon,
            check_input=check_input,
        )
    elif geometry.meter_type == "V-cone":
        c_used = DEFAULT_C_V_CONE if fixed_c is None else fixed_c
        c_source = "ISO 5167-5 default" if fixed_c is None else "Manual"
        flow = dpm.calculate_flow_V_cone(
            D=geometry.D_m,
            beta=geometry.beta,
            dP=dp_mbar,
            rho1=rho1,
            C=c_used,
            epsilon=epsilon,
            check_input=check_input,
        )
    else:
        if fixed_c is None and gas_state.viscosity_pa_s is None:
            raise DPFlowError(
                "An orifice discharge coefficient must either be given directly, or a dynamic "
                "viscosity must be available so the Reader-Harris/Gallagher equation can be solved."
            )
        if fixed_c is None and dp_mbar == 0.0:
            raise DPFlowError(
                "The Reader-Harris/Gallagher discharge coefficient is undefined at zero flow. "
                "Supply a fixed discharge coefficient for a zero-dP orifice calculation."
            )
        flow = dpm.calculate_flow_orifice(
            D=geometry.D_m,
            d=geometry.bore_m,
            dP=dp_mbar,
            rho1=rho1,
            mu=(
                gas_state.viscosity_pa_s
                if gas_state.viscosity_pa_s is not None
                else math.nan
            ),
            C=fixed_c,
            epsilon=epsilon,
            tapping=geometry.tapping,
            check_input=check_input,
        )
        # pvtlib only reports the discharge coefficient back when it solved for it,
        # so a caller-supplied C is carried through explicitly.
        c_used = fixed_c if fixed_c is not None else float(flow["C"])
        c_source = (
            "Manual"
            if fixed_c is not None
            else f"Reader-Harris/Gallagher ({geometry.tapping} tappings)"
        )

    mass_flow = float(flow["MassFlow"])
    volume_flow = float(flow["VolFlow"])
    velocity = float(flow["Velocity"])
    if not math.isfinite(mass_flow):
        raise DPFlowError("The DP meter calculation did not return a finite mass flow rate.")

    re_number = flow.get("Re")
    if re_number is None and gas_state.viscosity_pa_s is not None:
        re_number = reynolds_number(rho1, velocity, geometry.D_m, gas_state.viscosity_pa_s)
    re_value = float(re_number) if re_number is not None and math.isfinite(float(re_number)) else None

    std_volume_flow = mass_flow / gas_state.standard_density_kg_sm3

    warnings = _range_warnings(geometry, re_value, pressure_ratio)
    if geometry.meter_type == "Venturi" and fixed_c is not None:
        warnings.append(
            "Venturi geometry and Reynolds checks use the ISO 5167-4 as-cast "
            "construction range; verify construction-specific limits for this fixed C."
        )

    return DPFlowResult(
        meter_type=geometry.meter_type,
        beta=geometry.beta,
        discharge_coefficient=float(c_used),
        discharge_coefficient_source=c_source,
        expansibility=epsilon,
        expansibility_source=epsilon_source,
        reynolds_number=re_value,
        mass_flow_kg_h=mass_flow,
        volume_flow_m3_h=volume_flow,
        std_volume_flow_sm3_h=std_volume_flow,
        std_volume_flow_sm3_d=std_volume_flow * 24.0,
        velocity_m_s=velocity,
        differential_pressure_mbar=dp_mbar,
        pressure_ratio=pressure_ratio,
        gas_state=gas_state,
        warnings=tuple(warnings),
    )


def calculate_dp_flow_from_composition(
    composition: dict[str, float],
    geometry: MeterGeometry,
    dp_mbar: float,
    pressure: float,
    temperature: float,
    *,
    pressure_unit: str = "bara",
    temperature_unit: str = "C",
    equation: str = "GERG-2008",
    discharge_coefficient: float | None = None,
    expansibility: float | None = None,
    viscosity_pa_s: float | None = None,
) -> DPFlowResult:
    """Convenience wrapper: build the AGA8 gas state and calculate the DP meter flow."""
    gas_state = calculate_gas_state(
        composition,
        pressure,
        temperature,
        pressure_unit=pressure_unit,
        temperature_unit=temperature_unit,
        equation=equation,
        viscosity_pa_s=viscosity_pa_s,
    )
    return calculate_dp_flow(
        geometry,
        gas_state,
        dp_mbar,
        discharge_coefficient=discharge_coefficient,
        expansibility=expansibility,
    )


# ── Inverse calculation (sizing) ──────────────────────────────────────────────
def solve_dp_for_mass_flow(
    geometry: MeterGeometry,
    gas_state: GasState,
    target_mass_flow_kg_h: float,
    *,
    discharge_coefficient: float | None = None,
    expansibility: float | None = None,
    dp_max_mbar: float | None = None,
    tolerance: float = 1e-9,
    max_iterations: int = 200,
) -> DPFlowResult:
    """Solve for the differential pressure that gives a target mass flow rate.

    The mass flow is monotonically increasing in dP, so a bisection search is used.
    The result is the full :class:`DPFlowResult` at the solved dP, which keeps the
    discharge coefficient and expansibility consistent with the solution.
    """
    target = float(target_mass_flow_kg_h)
    if not math.isfinite(target) or target <= 0.0:
        raise DPFlowError("Target mass flow rate must be a finite number greater than zero.")
    try:
        tolerance = float(tolerance)
    except (TypeError, ValueError) as exc:
        raise DPFlowError(
            "Solver tolerance must be a finite number greater than zero."
        ) from exc
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise DPFlowError("Solver tolerance must be a finite number greater than zero.")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations <= 0:
        raise DPFlowError("Maximum solver iterations must be a positive integer.")

    # Mass flow only increases monotonically with dP while the expansibility correlation
    # stays inside its validated range (p2/p1 >= MIN_PRESSURE_RATIO), so the bisection
    # search is capped there rather than at the pressure where p2 reaches zero.
    ceiling = gas_state.pressure_bara * 1000.0 * (1.0 - MIN_PRESSURE_RATIO)
    if dp_max_mbar is None:
        upper = ceiling
    else:
        requested_upper = float(dp_max_mbar)
        if not math.isfinite(requested_upper) or requested_upper <= 0.0:
            raise DPFlowError(
                "The maximum differential pressure must be a finite number greater than zero."
            )
        upper = min(requested_upper, ceiling)

    def mass_flow_at(dp: float) -> float:
        return calculate_dp_flow(
            geometry,
            gas_state,
            dp,
            discharge_coefficient=discharge_coefficient,
            expansibility=expansibility,
        ).mass_flow_kg_h

    if mass_flow_at(upper) < target:
        raise DPFlowError(
            f"The target mass flow of {target:.4g} kg/h cannot be reached within the differential "
            f"pressure search limit of {upper:.4g} mbar (the lower of the given maximum dP and "
            f"{(1.0 - MIN_PRESSURE_RATIO) * 100:.0f} % of the upstream pressure, where the expansibility "
            "correlation is still valid). Increase the dP limit or use a smaller bore."
        )

    low, high = 0.0, upper
    for _ in range(max_iterations):
        mid = 0.5 * (low + high)
        value = mass_flow_at(mid)
        if abs(value - target) <= tolerance * target:
            break
        if value < target:
            low = mid
        else:
            high = mid
    else:
        raise DPFlowError(
            f"The differential-pressure solve did not converge within {max_iterations} iterations."
        )

    return calculate_dp_flow(
        geometry,
        gas_state,
        mid,
        discharge_coefficient=discharge_coefficient,
        expansibility=expansibility,
    )


def solve_dp_for_std_volume_flow(
    geometry: MeterGeometry,
    gas_state: GasState,
    target_std_volume_flow_sm3_h: float,
    **kwargs,
) -> DPFlowResult:
    """Solve for the dP that gives a target standard volume flow rate [Sm3/h]."""
    target = float(target_std_volume_flow_sm3_h)
    if not math.isfinite(target) or target <= 0.0:
        raise DPFlowError("Target standard volume flow rate must be a finite number greater than zero.")
    return solve_dp_for_mass_flow(
        geometry,
        gas_state,
        target * gas_state.standard_density_kg_sm3,
        **kwargs,
    )
