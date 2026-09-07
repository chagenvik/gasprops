"""Independent DP-meter cross-check: pvtlib gas properties + ``fluids`` ISO 5167 meters.

The gas state (density, isentropic exponent, standard density) comes from ``pvtlib``
AGA8, exactly as in the Gas Properties app, while the meter calculation is done with
the ISO 5167 implementations in the third-party ``fluids`` package instead of
``pvtlib.metering``. Running both and comparing the numbers is a manual quality check
of the gasprops DP-flow module.

Defaults are the gasprops "DP flow" page defaults:

    Pipe diameter D       200 mm
    Bore / cone diameter  120 mm
    Upstream pressure     60 bara
    Temperature           20 degC
    Differential pressure 500 mbar
    Orifice tapping       corner
    Equation of state     GERG-2008

Gas: pure methane (C1).

Run with::

    python scripts/dp_meter_crosscheck_fluids.py
"""

from __future__ import annotations

import math

import pvtlib
from fluids.flow_meter import (
    differential_pressure_meter_C_epsilon,
    differential_pressure_meter_solver,
)

# ── Default input (same as the gasprops DP flow page) ─────────────────────────
COMPOSITION = {"C1": 100.0}
EQUATION = "GERG-2008"

PIPE_DIAMETER_MM = 200.0
BORE_DIAMETER_MM = 170.0
PRESSURE_BARA = 100.0
TEMPERATURE_C = 20.0
DP_MBAR = 200.0
ORIFICE_TAPPING = "corner"

STANDARD_PRESSURE_BARA = 1.01325
STANDARD_TEMPERATURE_C = 15.0

#: Fallback viscosity if NeqSim is not available. Roughly methane at 60 bara, 20 degC.
FALLBACK_VISCOSITY_PA_S = 1.32e-5

#: gasprops meter type -> fluids meter type.
METERS = {
    "Venturi": "as cast convergent venturi tube",
    "Orifice": "ISO 5167 orifice",
    "V-cone": "cone meter",
}


def aga8_properties(pressure_bara: float, temperature_c: float) -> dict:
    """AGA8 properties of the gas at the given pressure and temperature."""
    return pvtlib.AGA8(EQUATION).calculate_from_PT(
        composition=COMPOSITION,
        pressure=pressure_bara,
        temperature=temperature_c,
        pressure_unit="bara",
        temperature_unit="C",
    )


def neqsim_viscosity(pressure_bara: float, temperature_c: float) -> float | None:
    """Gas-phase viscosity [Pa*s] from NeqSim (SRK), or None if NeqSim is unavailable."""
    try:
        from neqsim.thermo import TPflash, fluid

        gas = fluid("srk")
        gas.addComponent("methane", 100.0)
        gas.setMixingRule(2)
        gas.setTemperature(temperature_c, "C")
        gas.setPressure(pressure_bara, "bara")
        TPflash(gas)
        gas.initProperties()

        for index in range(int(gas.getNumberOfPhases())):
            phase = gas.getPhase(index)
            if "gas" not in str(phase.getPhaseTypeName()).lower():
                continue
            viscosity = float(phase.getPhysicalProperties().getViscosity())
            if math.isfinite(viscosity) and viscosity > 0.0:
                return viscosity
        return None
    except Exception:
        return None


def beta_ratio(meter_type: str, D: float, d: float) -> float:
    """Diameter ratio [-]. The cone meter uses the ISO 5167-5 definition."""
    if meter_type == "V-cone":
        return math.sqrt(1.0 - (d / D) ** 2)
    return d / D


def solve_meter(
    meter_type: str,
    D: float,
    d: float,
    rho1: float,
    mu: float,
    kappa: float,
    p1_pa: float,
    p2_pa: float,
) -> dict:
    """Mass flow, discharge coefficient and expansibility from ``fluids``."""
    fluids_meter = METERS[meter_type]
    taps = ORIFICE_TAPPING if meter_type == "Orifice" else None

    mass_flow_kg_s = differential_pressure_meter_solver(
        D=D,
        D2=d,
        P1=p1_pa,
        P2=p2_pa,
        rho=rho1,
        mu=mu,
        k=kappa,
        meter_type=fluids_meter,
        taps=taps,
    )
    C, epsilon = differential_pressure_meter_C_epsilon(
        D=D,
        D2=d,
        m=mass_flow_kg_s,
        P1=p1_pa,
        P2=p2_pa,
        rho=rho1,
        mu=mu,
        k=kappa,
        meter_type=fluids_meter,
        taps=taps,
    )

    pipe_area = 0.25 * math.pi * D**2
    velocity = mass_flow_kg_s / (rho1 * pipe_area)

    return {
        "beta": beta_ratio(meter_type, D, d),
        "C": C,
        "epsilon": epsilon,
        "mass_flow_kg_s": mass_flow_kg_s,
        "velocity_m_s": velocity,
        "reynolds": rho1 * velocity * D / mu,
    }


def main() -> None:
    D = PIPE_DIAMETER_MM / 1000.0
    d = BORE_DIAMETER_MM / 1000.0
    p1_pa = PRESSURE_BARA * 1e5
    p2_pa = p1_pa - DP_MBAR * 100.0

    gas = aga8_properties(PRESSURE_BARA, TEMPERATURE_C)
    standard = aga8_properties(STANDARD_PRESSURE_BARA, STANDARD_TEMPERATURE_C)
    rho1 = float(gas["rho"])
    kappa = float(gas["kappa"])
    rho_standard = float(standard["rho"])

    viscosity = neqsim_viscosity(PRESSURE_BARA, TEMPERATURE_C)
    viscosity_source = "NeqSim (SRK)"
    if viscosity is None:
        viscosity = FALLBACK_VISCOSITY_PA_S
        viscosity_source = "fallback constant"

    print("DP meter cross-check: pvtlib AGA8 gas properties + fluids ISO 5167 meters")
    print("=" * 78)
    print("Input")
    print(f"  Gas                    100 mol% C1 ({EQUATION})")
    print(f"  Pipe diameter D        {PIPE_DIAMETER_MM:.3f} mm")
    print(f"  Bore / cone diameter   {BORE_DIAMETER_MM:.3f} mm")
    print(f"  Upstream pressure p1   {PRESSURE_BARA:.4f} bara")
    print(f"  Temperature T1         {TEMPERATURE_C:.4f} degC")
    print(f"  Differential pressure  {DP_MBAR:.2f} mbar")
    print(f"  Orifice tapping        {ORIFICE_TAPPING}")
    print()
    print("Gas properties from pvtlib AGA8")
    print(f"  Density rho1           {rho1:.6f} kg/m3")
    print(f"  Isentropic exponent    {kappa:.6f} -")
    print(f"  Compressibility Z      {float(gas['z']):.6f} -")
    print(f"  Molar mass             {float(gas['mm']):.6f} g/mol")
    print(f"  Speed of sound         {float(gas['w']):.4f} m/s")
    print(
        f"  Standard density       {rho_standard:.6f} kg/Sm3 "
        f"({STANDARD_PRESSURE_BARA:g} bara, {STANDARD_TEMPERATURE_C:g} degC)"
    )
    print(f"  Viscosity mu           {viscosity:.6e} Pa*s ({viscosity_source})")
    print()

    header = (
        f"{'Meter':<10}{'beta':>9}{'C':>10}{'epsilon':>10}{'Re':>13}"
        f"{'kg/h':>14}{'m3/h':>12}{'Sm3/h':>14}{'Sm3/d':>15}{'m/s':>9}"
    )
    print("Results from fluids (ISO 5167)")
    print(header)
    print("-" * len(header))

    for meter_type in METERS:
        result = solve_meter(meter_type, D, d, rho1, viscosity, kappa, p1_pa, p2_pa)
        mass_flow_kg_h = result["mass_flow_kg_s"] * 3600.0
        volume_flow_m3_h = mass_flow_kg_h / rho1
        std_flow_sm3_h = mass_flow_kg_h / rho_standard
        print(
            f"{meter_type:<10}"
            f"{result['beta']:>9.5f}"
            f"{result['C']:>10.5f}"
            f"{result['epsilon']:>10.5f}"
            f"{result['reynolds']:>13.3e}"
            f"{mass_flow_kg_h:>14.2f}"
            f"{volume_flow_m3_h:>12.3f}"
            f"{std_flow_sm3_h:>14.1f}"
            f"{std_flow_sm3_h * 24.0:>15.1f}"
            f"{result['velocity_m_s']:>9.3f}"
        )

    print()
    print("Notes")
    print("  * Venturi C is the ISO 5167-4 as-cast value (0.984), V-cone C the ISO 5167-5")
    print("    default (0.82); the orifice C is solved with Reader-Harris/Gallagher.")
    print("  * The V-cone beta uses sqrt(1 - (dc/D)^2), so beta = 0.8 with the default")
    print("    geometry, which is outside the ISO 5167-5 range of use (0.45 - 0.75).")
    print("  * Velocity and Reynolds number are referred to the upstream pipe diameter D.")


if __name__ == "__main__":
    main()
