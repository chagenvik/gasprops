# gasprops

[![Streamlit app](https://img.shields.io/badge/streamlit-app-ff4b4b?logo=streamlit&logoColor=white)](https://gasprops.radix.equinor.com/)
[![python](https://img.shields.io/badge/python-3.11-blue)](runtime.txt)
[![Tests](https://github.com/chagenvik/gasprops/actions/workflows/pytest.yml/badge.svg)](https://github.com/chagenvik/gasprops/actions/workflows/pytest.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Streamlit app for gas property analysis using AGA8 and NeqSim workflows.

## Run locally

```bash
streamlit run streamlit_app.py
```

## App layout

- **Tabbed views** for all gas-property pages
- **Shared AGA8 composition editor** at the top of the app
- **Direct use of `pvtlib`, `neqsim-python`, and `uncertaintylib`**
- The AGA8 DETAIL and GERG-2008 implementations used through `pvtlib` are based on the official [NIST AGA8 reference repository](https://github.com/usnistgov/AGA8), via the Rust [aga8 crate](https://crates.io/crates/aga8)

## Calculation Scope

- **AGA8 DETAIL / GERG-2008 (primary engine):** Used for most property workflows (single-point, multi-point, tables, surfaces, uncertainty, flow metering, comparison, validation, and mixing). These calculations are intended for **single-phase gas**.
- **NeqSim workflows:** Used in **Flash Calculation** and **Phase Envelope** tabs for phase-behavior analysis, and to supply the gas viscosity in the **DP Flow Meter** tab (AGA8 does not model viscosity).
- **Composition constraint:** The app input is constrained to the **21-component AGA8 component set**.

## Included views

- Single Calculation
- Multi-Point Calculation
- Mix
- Property Tables
- 3D plot
- Uncertainty Analysis
- AGA8 EoS Comparison
- AGA8 Validation
- AGA8 vs REFPROP
- Flash Calculation
- Phase Envelope
- DP Flow Meter
- Flow Converter

The two flow-metering tabs sit at the end of the tab bar and are colour-coded separately from the
AGA8 gas-property tabs and the NeqSim phase-behaviour tabs.

## DP Flow Meter

Calculates the flow rate through differential-pressure meters using the ISO 5167 models in
`pvtlib`, with AGA8 supplying the upstream density, isentropic exponent and standard density:

| Meter | Standard | Discharge coefficient |
| --- | --- | --- |
| Venturi tube | ISO 5167-4:2022 | Fixed (0.984 as cast) or calibrated value |
| Orifice plate | ISO 5167-2:2022 | Reader-Harris/Gallagher, solved iteratively |
| V-cone | ISO 5167-5:2022 | 0.82 uncalibrated, or calibrated value |

The tab supports single-point, multi-point and inverse (solve for Δp) workflows, converts mass
flow to Sm³/h and Sm³/d at 1.01325 bara / 15 °C, and flags ISO 5167 range-of-use violations.
Venturi range checks use the as-cast construction envelope; selecting another fixed coefficient
also emits a reminder to verify its construction-specific limits. Parameter diagrams for each
meter type are in `assets/dp_meters/`.

The calculation engine lives in `src/gasprop/dp_flow.py` and is free of Streamlit, so it can be
used directly:

```python
from gasprop.dp_flow import MeterGeometry, calculate_dp_flow_from_composition

geometry = MeterGeometry(meter_type="Venturi", pipe_diameter_mm=200.0, bore_diameter_mm=120.0)
result = calculate_dp_flow_from_composition(
    {"C1": 90.0, "C2": 5.0, "C3": 2.0, "N2": 1.5, "CO2": 1.5},
    geometry,
    dp_mbar=500.0,
    pressure=60.0,
    temperature=20.0,
)
print(result.std_volume_flow_sm3_h)
```

## Flow Converter

Converts a single flow rate between **mass flow**, **actual (line-condition) volume flow** and
**standard volume flow**, using AGA8 densities at the line conditions and at the reference state:

```text
actual volume flow   = mass flow / rho(P, T)
standard volume flow = mass flow / rho(P_std, T_std)
```

Standard conditions default to 1.01325 bara / 15 °C (ISO 13443, Sm³) with presets for normal
conditions (Nm³, 0 °C) and US standard conditions (60 °F), plus a fully custom option. Results are
reported per second, per hour and per day; mass flow can be entered in kg or tonnes.

The engine lives in `src/gasprop/flow_converter.py` and is free of Streamlit:

```python
from gasprop.flow_converter import StandardConditions, convert_flow

result = convert_flow(
    {"C1": 90.0, "C2": 5.0, "C3": 2.0, "N2": 1.5, "CO2": 1.5},
    100_000.0,
    "mass",
    pressure=60.0,
    temperature=20.0,
    time_unit="h",
    standard_conditions=StandardConditions(1.01325, 15.0),
)
mass_per_day, actual_per_day, standard_per_day = result.in_time_unit("d")
```

## Repository structure

```text
streamlit_app.py
src/gasprop/
data/examples/
tests/
```

## Notes

- Example gas compositions are bundled in `data/examples/`.
- Imported compositions are normalized to the AGA8 composition table used by the original app.
- The app is designed for Streamlit Community Cloud.
- NeqSim-backed views require Java on the deployment target; Streamlit Cloud support is configured via `packages.txt`.

## Legal

- This app is provided **as-is**, without warranty.
- It is for informational use only and is **not** a certified engineering or operational decision tool.
- Users are responsible for independent verification before any safety-critical, operational, financial, or regulatory use.
- Terms of Use: see [TERMS_OF_USE.md](TERMS_OF_USE.md).
- License: MIT (see [LICENSE](LICENSE)).
