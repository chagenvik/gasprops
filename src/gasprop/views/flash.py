"""Flash calculation view powered by NeqSim."""

from __future__ import annotations

import io
from collections.abc import Callable

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from ..composition_input import export_composition_values_to_canonical_csv
from ..domain import NEQSIM_NAMES as _NEQSIM_NAMES
from utils.session_fluids import FORMAT_AGA8
from utils.session_fluids_ui import render_temporary_save_button

EOS_OPTIONS: dict[str, str] = {
    "SRK (Soave-Redlich-Kwong)": "srk",
    "PR (Peng-Robinson)": "pr",
    "UMR-PRU (recommended for HC dew point)": "pr-umr",
    "CPA-SRK": "cpa",
}

CUBIC_MODELS = {"srk", "pr", "pr-umr", "cpa"}

PHASE_OPTIONS = ["gas", "liquid", "aqueous"]

PHASE_LABELS = {
    "gas": "Gas",
    "liquid": "Liquid",
    "aqueous": "Aqueous",
}

PROPERTIES = {
    "density": ("Density", "kg/m3"),
    "molar_mass": ("Molar Mass", "g/mol"),
    "z": ("Compressibility Factor", "-"),
    "speed_of_sound": ("Speed of Sound", "m/s"),
    "viscosity": ("Viscosity", "Pa*s"),
    "kinematic_viscosity": ("Kinematic Viscosity", "m2/s"),
    "cp": ("Isobaric Heat Capacity", "J/(mol*K)"),
    "cv": ("Isochoric Heat Capacity", "J/(mol*K)"),
    "enthalpy": ("Enthalpy", "J/mol"),
    "entropy": ("Entropy", "J/(mol*K)"),
}

DEFAULT_PROPERTIES = ["density", "molar_mass", "z", "speed_of_sound", "viscosity"]
_STATE_FLASH = "gp_flash_result"

_DEFAULT_POINTS = pd.DataFrame(
    {
        "Pressure": [5.0, 20.0, 50.0, 100.0],
        "Temperature": [20.0, 20.0, 20.0, 20.0],
    }
)


def _inverse_component_map() -> dict[str, str]:
    inv: dict[str, str] = {}
    for aga8_name, neqsim_name in _NEQSIM_NAMES.items():
        inv[neqsim_name.lower()] = aga8_name
    return inv


def _normalise_composition(composition: dict[str, float]) -> dict[str, float]:
    total = sum(v for v in composition.values() if v > 0.0)
    if total <= 0.0:
        return {}
    return {k: v / total for k, v in composition.items() if v > 0.0}


def _phase_bucket(phase_name: str) -> str:
    lower = (phase_name or "").lower()
    if "gas" in lower:
        return "gas"
    if "aqueous" in lower or "water" in lower:
        return "aqueous"
    return "liquid"


def _phase_properties(phase) -> dict[str, float | None]:
    props: dict[str, float | None] = {k: None for k in PROPERTIES}
    try:
        phys = phase.getPhysicalProperties()
    except Exception:
        phys = None

    try:
        if phys is not None:
            props["density"] = float(phys.getDensity())
    except Exception:
        pass

    try:
        props["molar_mass"] = float(phase.getMolarMass()) * 1000.0
    except Exception:
        pass

    try:
        props["z"] = float(phase.getZ())
    except Exception:
        pass

    try:
        props["speed_of_sound"] = float(phase.getSoundSpeed())
    except Exception:
        pass

    try:
        if phys is not None:
            props["viscosity"] = float(phys.getViscosity())
    except Exception:
        pass

    # Kinematic viscosity: nu = mu / rho
    try:
        mu = props.get("viscosity")
        rho = props.get("density")
        if mu is not None and rho is not None and rho > 0.0:
            props["kinematic_viscosity"] = float(mu) / float(rho)
    except Exception:
        pass

    try:
        props["cp"] = float(phase.getCp())
    except Exception:
        pass

    try:
        props["cv"] = float(phase.getCv())
    except Exception:
        pass

    try:
        props["enthalpy"] = float(phase.getEnthalpy())
    except Exception:
        pass

    try:
        props["entropy"] = float(phase.getEntropy())
    except Exception:
        pass

    return props


def _phase_composition(phase, inverse_map: dict[str, str]) -> dict[str, float]:
    values: dict[str, float] = {}
    for idx in range(int(phase.getNumberOfComponents())):
        comp = phase.getComponent(idx)
        raw_name = str(comp.getComponentName())
        aga8_name = inverse_map.get(raw_name.lower())
        if aga8_name is None:
            continue
        frac = float(comp.getx())
        if frac > 0.0:
            values[aga8_name] = frac * 100.0
    total = sum(values.values())
    if total <= 0.0:
        return values
    return {k: v * 100.0 / total for k, v in values.items()}


def _run_flash(
    composition: dict[str, float],
    points: list[tuple[float, float]],
    eos_model: str,
    pressure_unit: str,
    temperature_unit: str,
    selected_phases: list[str],
    selected_properties: list[str],
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[pd.DataFrame, dict[int, dict[str, dict[str, float]]], list[str]]:
    from neqsim.thermo import TPflash, fluid

    inverse_map = _inverse_component_map()
    comp = _normalise_composition(composition)
    errors: list[str] = []
    phase_comp_by_row: dict[int, dict[str, dict[str, float]]] = {}
    records: list[dict[str, float | str | bool | None]] = []

    # Build one fluid per run/EOS and reuse it across all P/T points.
    gas_fluid = fluid(eos_model)
    for comp_name, frac in comp.items():
        gas_fluid.addComponent(_NEQSIM_NAMES[comp_name], frac)
    gas_fluid.setMixingRule(2)

    total_points = len(points)
    for row_idx, (pressure, temperature) in enumerate(points, start=1):
        try:
            gas_fluid.setTemperature(float(temperature), temperature_unit)
            gas_fluid.setPressure(float(pressure), pressure_unit)
            TPflash(gas_fluid)
            gas_fluid.initProperties()

            phase_data: dict[str, dict[str, float | None]] = {}
            phase_compositions: dict[str, dict[str, float]] = {}
            phase_fraction: dict[str, float] = {name: 0.0 for name in PHASE_OPTIONS}

            n_phases = int(gas_fluid.getNumberOfPhases())
            for i in range(n_phases):
                phase = gas_fluid.getPhase(i)
                phase_type = _phase_bucket(str(phase.getPhaseTypeName()))
                phase_fraction[phase_type] += float(phase.getBeta())
                if phase_type not in phase_data:
                    phase_data[phase_type] = _phase_properties(phase)
                    phase_compositions[phase_type] = _phase_composition(phase, inverse_map)

            status_parts = [
                PHASE_LABELS[p]
                for p in PHASE_OPTIONS
                if phase_fraction[p] > 1e-10
            ]
            status = " + ".join(status_parts) if status_parts else "Unknown"

            has_liquid = phase_fraction["liquid"] > 1e-10 or phase_fraction["aqueous"] > 1e-10

            row: dict[str, float | str | bool | None] = {
                "Input Row": row_idx,
                f"Pressure [{pressure_unit}]": pressure,
                f"Temperature [{'°C' if temperature_unit == 'C' else 'K'}]": temperature,
                "Phase Status": status,
                "Liquid present": has_liquid,
            }

            for phase_name in selected_phases:
                row[f"{PHASE_LABELS[phase_name]} present"] = phase_fraction[phase_name] > 1e-10
                row[f"{PHASE_LABELS[phase_name]} mole fraction [-]"] = phase_fraction[phase_name]
                for prop in selected_properties:
                    name, unit = PROPERTIES[prop]
                    key = f"{PHASE_LABELS[phase_name]} {name} [{unit}]"
                    row[key] = phase_data.get(phase_name, {}).get(prop)

            records.append(row)
            phase_comp_by_row[row_idx] = phase_compositions
        except Exception as exc:
            errors.append(
                f"Row {row_idx} (P={pressure} {pressure_unit}, T={temperature} {temperature_unit}) failed: {exc}"
            )
        finally:
            if progress_callback is not None:
                progress_callback(row_idx, total_points)

    return pd.DataFrame(records), phase_comp_by_row, errors


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
        key="flash_plot_mode",
    )

    numeric_cols = [
        c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
    ]
    categorical_cols = [
        c for c in df.columns if c not in numeric_cols
    ]

    pressure_col = next((c for c in df.columns if c.startswith("Pressure [")), None)
    gas_density_col = next((c for c in df.columns if c.startswith("Gas Density [")), None)
    gas_z_col = next((c for c in df.columns if c.startswith("Gas Compressibility Factor [")), None)

    default_x = pressure_col if pressure_col in numeric_cols else (numeric_cols[0] if numeric_cols else None)
    default_y = gas_density_col if gas_density_col in numeric_cols else (numeric_cols[1] if len(numeric_cols) > 1 else default_x)

    color_options = ["None"] + numeric_cols + categorical_cols
    default_color = gas_z_col if gas_z_col in color_options else (numeric_cols[2] if len(numeric_cols) > 2 else "None")

    if default_x is None:
        st.info("No numeric result columns available for plotting.")
        return

    default_x_idx = numeric_cols.index(default_x)
    default_y_idx = numeric_cols.index(default_y) if default_y in numeric_cols else default_x_idx
    default_color_idx = color_options.index(default_color) if default_color in color_options else 0

    color_scale_options = ["Viridis", "Plasma", "Inferno", "Magma", "Cividis", "Turbo"]
    default_color_scale_idx = 0

    if plot_mode == "2D":
        c1, c2, c3, c4 = st.columns(4)
        x_col = c1.selectbox("X axis", numeric_cols, index=default_x_idx, key="flash_plot2d_x")
        y_col = c2.selectbox("Y axis", numeric_cols, index=default_y_idx, key="flash_plot2d_y")
        color_col = c3.selectbox("Color by", options=color_options, index=default_color_idx, key="flash_plot2d_color")
        color_scale = c4.selectbox("Color palette", options=color_scale_options, index=default_color_scale_idx, key="flash_plot2d_colorscale")

        color_is_numeric = color_col in numeric_cols

        fig = px.scatter(
            df,
            x=x_col,
            y=y_col,
            color=None if color_col == "None" else color_col,
            color_continuous_scale=color_scale if color_is_numeric else None,
            hover_data=["Input Row", "Phase Status"],
        )
        fig.update_layout(height=520)
        st.plotly_chart(fig, width='stretch')
    else:
        if len(numeric_cols) < 3:
            st.info("Need at least three numeric columns for 3D plot.")
            return

        default_z = numeric_cols[2] if len(numeric_cols) > 2 else numeric_cols[-1]
        default_z_idx = numeric_cols.index(default_z)

        c1, c2, c3, c4, c5 = st.columns(5)
        x_col = c1.selectbox("X axis", numeric_cols, index=default_x_idx, key="flash_plot3d_x")
        y_col = c2.selectbox("Y axis", numeric_cols, index=default_y_idx, key="flash_plot3d_y")
        z_col = c3.selectbox("Z axis", numeric_cols, index=default_z_idx, key="flash_plot3d_z")
        color_col = c4.selectbox("Color by", options=color_options, index=default_color_idx, key="flash_plot3d_color")
        color_scale = c5.selectbox("Color palette", options=color_scale_options, index=default_color_scale_idx, key="flash_plot3d_colorscale")

        color_is_numeric = color_col in numeric_cols

        fig = px.scatter_3d(
            df,
            x=x_col,
            y=y_col,
            z=z_col,
            color=None if color_col == "None" else color_col,
            color_continuous_scale=color_scale if color_is_numeric else None,
            hover_data=["Input Row", "Phase Status"],
        )
        fig.update_layout(height=650)
        st.plotly_chart(fig, width='stretch')


def _render_phase_composition_tools(
    phase_comp_by_row: dict[int, dict[str, dict[str, float]]],
    pressure_unit: str,
    temperature_unit: str,
    results_df: pd.DataFrame,
) -> None:
    if not phase_comp_by_row:
        return

    st.markdown("#### Output phase compositions")
    row_options = sorted(phase_comp_by_row)
    selected_row = st.selectbox("Select result row", row_options, key="flash_phase_row")

    phase_map = phase_comp_by_row[selected_row]
    available_phases = [p for p in PHASE_OPTIONS if p in phase_map and phase_map[p]]
    if not available_phases:
        st.info("No phase composition available for this row.")
        return

    selected_phase = st.selectbox(
        "Select phase composition",
        options=available_phases,
        format_func=lambda p: PHASE_LABELS[p],
        key="flash_phase_pick",
    )

    selected_composition = phase_map[selected_phase]
    comp_df = pd.DataFrame(
        {
            "Component": list(selected_composition.keys()),
            "MolePercent": list(selected_composition.values()),
        }
    ).sort_values("MolePercent", ascending=False)
    st.dataframe(comp_df, width='stretch', hide_index=True)

    row_data = results_df[results_df["Input Row"] == selected_row].iloc[0]
    p_col = f"Pressure [{pressure_unit}]"
    t_col = f"Temperature [{'°C' if temperature_unit == 'C' else 'K'}]"

    def _csv_provider() -> str:
        return export_composition_values_to_canonical_csv(selected_composition)

    def _name_provider() -> str:
        return (
            f"Flash {PHASE_LABELS[selected_phase]} P={row_data[p_col]:.3g} {pressure_unit} "
            f"T={row_data[t_col]:.3g} {('°C' if temperature_unit == 'C' else 'K')}"
        )

    render_temporary_save_button(
        key="flash_save_phase_comp",
        canonical_csv_provider=_csv_provider,
        format_family=FORMAT_AGA8,
        source_module="Flash Calculation",
        source_context=f"row={selected_row}, phase={selected_phase}",
        base_name_provider=_name_provider,
        label=f"💾 Save {PHASE_LABELS[selected_phase]} composition as temporary fluid",
    )


def render(composition: dict | None) -> None:
    """Render NeqSim flash calculations for custom points or P/T ranges."""
    st.subheader("Flash Calculation")
    st.caption(
        "Run TP flash with NeqSim for AGA8-component mixtures, inspect gas/liquid/aqueous outputs, and visualise results."
    )

    if composition is None:
        st.info("Enter a valid composition above to enable flash calculations.")
        return

    st.info(
        "Only the AGA8 default component set is supported in this module because it reuses the shared AGA8 composition input.",
        icon="ℹ️",
    )

    c1, c2, c3 = st.columns(3)
    eos_label = c1.selectbox("Equation of state", options=list(EOS_OPTIONS.keys()), index=0, key="flash_eos")
    pressure_unit = c2.selectbox("Pressure unit", ["bara", "barg", "kPa", "MPa"], index=0, key="flash_p_unit")
    temperature_unit = c3.selectbox(
        "Temperature unit",
        ["C", "K"],
        index=0,
        key="flash_t_unit",
        format_func=lambda x: "°C" if x == "C" else "K",
    )

    eos_model = EOS_OPTIONS[eos_label]
    if eos_model in CUBIC_MODELS:
        st.warning(
            "Warning: transport and thermodynamic properties from cubic equations of state can be quite inaccurate, "
            "especially near phase boundaries and for liquid-rich conditions. Validate critical decisions against a "
            "higher-fidelity model or trusted reference data.",
            icon="⚠️",
        )

    p1, p2 = st.columns(2)
    selected_phases = p1.multiselect(
        "Output phases",
        options=PHASE_OPTIONS,
        default=["gas"],
        format_func=lambda p: PHASE_LABELS[p],
        key="flash_phase_select",
    )
    selected_properties = p2.multiselect(
        "Output properties",
        options=list(PROPERTIES.keys()),
        default=DEFAULT_PROPERTIES,
        format_func=lambda p: f"{PROPERTIES[p][0]} [{PROPERTIES[p][1]}]",
        key="flash_prop_select",
    )

    if not selected_phases:
        st.warning("Select at least one phase.")
        return
    if not selected_properties:
        st.warning("Select at least one property.")
        return

    mode = st.radio(
        "Input mode",
        options=["Input table", "Pressure/temperature ranges"],
        horizontal=True,
        key="flash_input_mode",
    )

    points: list[tuple[float, float]] = []
    temp_label = "°C" if temperature_unit == "C" else "K"

    if mode == "Input table":
        st.markdown(
            f"#### Operating points  ·  Pressure [{pressure_unit}]  ·  Temperature [{temp_label}]"
        )
        input_df = st.data_editor(
            _DEFAULT_POINTS.rename(
                columns={
                    "Pressure": f"Pressure [{pressure_unit}]",
                    "Temperature": f"Temperature [{temp_label}]",
                }
            ),
            key="flash_input_table",
            width='stretch',
            hide_index=True,
            num_rows="dynamic",
            column_config={
                f"Pressure [{pressure_unit}]": st.column_config.NumberColumn(
                    f"Pressure [{pressure_unit}]", min_value=0.0, step=0.1, format="%.3f"
                ),
                f"Temperature [{temp_label}]": st.column_config.NumberColumn(
                    f"Temperature [{temp_label}]", step=0.5, format="%.3f"
                ),
            },
        )
        p_col = f"Pressure [{pressure_unit}]"
        t_col = f"Temperature [{temp_label}]"
        valid = input_df.dropna(subset=[p_col, t_col])
        points = [(float(r[p_col]), float(r[t_col])) for _, r in valid.iterrows()]
    else:
        st.markdown("#### Pressure range")
        cp1, cp2, cp3 = st.columns(3)
        p_min = cp1.number_input("P min", min_value=0.0, value=5.0, step=1.0, format="%.3f", key="flash_pmin")
        p_max = cp2.number_input("P max", min_value=0.0, value=200.0, step=1.0, format="%.3f", key="flash_pmax")
        p_step = cp3.number_input("P step", min_value=0.01, value=5.0, step=1.0, format="%.3f", key="flash_pstep")

        st.markdown(f"#### Temperature range [{temp_label}]")
        ct1, ct2, ct3 = st.columns(3)
        t_floor = -273.15 if temperature_unit == "C" else 0.0
        t_default_min = 0.0 if temperature_unit == "C" else 273.15
        t_default_max = 100.0 if temperature_unit == "C" else 373.15
        t_min = ct1.number_input("T min", min_value=t_floor, value=t_default_min, step=1.0, format="%.3f", key="flash_tmin")
        t_max = ct2.number_input("T max", min_value=t_floor, value=t_default_max, step=1.0, format="%.3f", key="flash_tmax")
        t_step = ct3.number_input("T step", min_value=0.01, value=5.0, step=1.0, format="%.3f", key="flash_tstep")

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

    cached = st.session_state.get(_STATE_FLASH)
    has_cache = cached is not None
    run_label = "Run flash calculations" if not has_cache else "Re-run flash calculations"
    run = st.button(run_label, type="primary", key="flash_run_btn")

    if run:
        if not points:
            st.warning("No valid pressure/temperature points found.")
        else:
            progress = st.progress(0, text=f"Running flash calculations... 0/{len(points)}")
            with st.spinner(f"Running flash calculations for {len(points)} point(s)..."):
                result_df, phase_comp_by_row, errors = _run_flash(
                    composition=composition,
                    points=points,
                    eos_model=eos_model,
                    pressure_unit=pressure_unit,
                    temperature_unit=temperature_unit,
                    selected_phases=selected_phases,
                    selected_properties=selected_properties,
                    progress_callback=lambda i, n: progress.progress(i / n, text=f"Running flash calculations... {i}/{n}"),
                )
            progress.empty()

            if result_df.empty:
                st.error("No successful flash calculations.")
            else:
                st.session_state[_STATE_FLASH] = {
                    "result_df": result_df,
                    "phase_comp_by_row": phase_comp_by_row,
                    "errors": errors,
                    "eos_label": eos_label,
                    "eos_model": eos_model,
                    "pressure_unit": pressure_unit,
                    "temperature_unit": temperature_unit,
                }

    state = st.session_state.get(_STATE_FLASH)
    if state is None:
        return

    result_df = state["result_df"]
    phase_comp_by_row = state["phase_comp_by_row"]
    errors = state["errors"]
    result_eos_label = state["eos_label"]
    result_eos_model = state["eos_model"]
    result_pressure_unit = state["pressure_unit"]
    result_temperature_unit = state["temperature_unit"]

    if errors:
        with st.expander(f"{len(errors)} point(s) failed"):
            for err in errors:
                st.error(err)

    if not run:
        st.caption("Showing most recent flash results. Click Re-run flash calculations to update.")

    n_liquid = int(result_df["Liquid present"].sum())
    if n_liquid > 0:
        st.warning(
            f"Liquid or aqueous phase detected in {n_liquid} of {len(result_df)} calculated point(s).",
            icon="⚠️",
        )

    st.success(f"Calculated {len(result_df)} point(s) with {result_eos_label}.")
    st.caption("Phase fractions are reported as NeqSim phase mole fractions (beta), unitless [-].")
    st.dataframe(result_df, width='stretch', hide_index=True)

    csv_buffer = io.BytesIO()
    result_df.to_csv(csv_buffer, index=False)
    st.download_button(
        label="Download flash results (CSV)",
        data=csv_buffer.getvalue(),
        file_name=f"flash_results_{result_eos_model}.csv",
        mime="text/csv",
        key="flash_dl_csv",
    )

    _plot_results(result_df)
    _render_phase_composition_tools(
        phase_comp_by_row=phase_comp_by_row,
        pressure_unit=result_pressure_unit,
        temperature_unit=result_temperature_unit,
        results_df=result_df,
    )
