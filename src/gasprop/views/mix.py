"""Mix view for combining two AGA8 gas compositions."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import streamlit as st

from ..composition import available_example_names, composition_from_csv_text, composition_to_csv, load_example_composition
from ..mix_logic import MixBasis, MixResult, mix_range, mix_two
from utils.session_fluids import FORMAT_AGA8, list_session_fluids
from utils.session_fluids_ui import render_temporary_save_button

_MIX_BASIS_LABELS: dict[MixBasis, str] = {
    "mass": "Mass [kg]",
    "mole": "Moles [kmol]",
    "volume": "Volume [m3]",
    "std_volume": "Standard volume [Sm3]",
}

_SINGLE_LABELS: dict[MixBasis, tuple[str, str]] = {
    "mass": ("Amount of fluid 1 [kg]", "Amount of fluid 2 [kg]"),
    "mole": ("Amount of fluid 1 [kmol]", "Amount of fluid 2 [kmol]"),
    "volume": ("Volume of fluid 1 [m3]", "Volume of fluid 2 [m3]"),
    "std_volume": ("Std. volume of fluid 1 [Sm3]", "Std. volume of fluid 2 [Sm3]"),
}

_TOTAL_LABELS: dict[MixBasis, str] = {
    "mass": "Total amount [kg]",
    "mole": "Total amount [kmol]",
    "volume": "Total volume [m3]",
    "std_volume": "Total std. volume [Sm3]",
}

_SINGLE_STATE_KEY = "mix_single_result"
_RANGE_STATE_KEY = "mix_range_results"


def _fluid_options_from_sources(active_composition: dict[str, float]) -> dict[str, dict[str, float]]:
    options: dict[str, dict[str, float]] = {
        "Current composition": dict(active_composition),
    }

    for name in available_example_names():
        try:
            options[f"Example: {name}"] = load_example_composition(name)
        except Exception:
            continue

    for saved in list_session_fluids(format_family=FORMAT_AGA8):
        try:
            options[f"Saved: {saved.display_name}"] = composition_from_csv_text(saved.canonical_csv)
        except Exception:
            continue

    return options


def _render_fluid_selectors(active_composition: dict[str, float]) -> tuple[str, dict[str, float], str, dict[str, float]] | None:
    options = _fluid_options_from_sources(active_composition)
    if len(options) < 2:
        st.warning("Need at least two valid AGA8 fluids. Save another fluid or use an example gas.")
        return None

    labels = list(options.keys())
    col1, col2 = st.columns(2)
    with col1:
        fluid1_name = st.selectbox("Fluid 1", options=labels, index=0, key="mix_fluid1")
    with col2:
        default_2 = 1 if len(labels) > 1 else 0
        fluid2_name = st.selectbox("Fluid 2", options=labels, index=default_2, key="mix_fluid2")

    if fluid1_name == fluid2_name:
        st.info("Select two different fluids to create a meaningful mix.")

    return fluid1_name, options[fluid1_name], fluid2_name, options[fluid2_name]


def _render_basis_controls(key_prefix: str) -> tuple[MixBasis, dict[str, float]]:
    label = st.radio(
        "Mixing basis",
        options=list(_MIX_BASIS_LABELS.values()),
        horizontal=True,
        key=f"{key_prefix}_basis",
    )
    basis = next(k for k, v in _MIX_BASIS_LABELS.items() if v == label)

    params: dict[str, float] = {}
    if basis == "volume":
        col_p, col_t = st.columns(2)
        with col_p:
            params["p_barg"] = st.number_input(
                "Pressure [barg]",
                value=0.0,
                min_value=-1.01325,
                step=1.0,
                key=f"{key_prefix}_p_barg",
            )
        with col_t:
            params["t_c"] = st.number_input(
                "Temperature [C]",
                value=15.0,
                min_value=-273.15,
                step=1.0,
                key=f"{key_prefix}_t_c",
            )
    elif basis == "std_volume":
        st.caption("Reference conditions: 15 C, 1.01325 bara (0.0 barg).")

    return basis, params


def _fmt(value: float | None, decimals: int = 4) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and math.isnan(value):
        return "-"
    return f"{value:.{decimals}f}"


def _render_mix_result(result: MixResult, key_prefix: str) -> None:
    st.markdown(f"**{result.label}**")

    summary_rows = [
        {
            "Fluid": result.fluid1_name,
            "Mass [kg]": _fmt(result.mass1_kg),
            "Moles [kmol]": _fmt(result.moles1_kmol, 6),
            "Molar mass [kg/kmol]": _fmt(result.mw1_kg_per_kmol, 6),
            "Density used [kg/m3]": _fmt(result.density1_used_kg_m3, 6),
        },
        {
            "Fluid": result.fluid2_name,
            "Mass [kg]": _fmt(result.mass2_kg),
            "Moles [kmol]": _fmt(result.moles2_kmol, 6),
            "Molar mass [kg/kmol]": _fmt(result.mw2_kg_per_kmol, 6),
            "Density used [kg/m3]": _fmt(result.density2_used_kg_m3, 6),
        },
        {
            "Fluid": "Combined",
            "Mass [kg]": _fmt(result.total_mass_kg),
            "Moles [kmol]": _fmt(result.total_moles_kmol, 6),
            "Molar mass [kg/kmol]": _fmt(result.mixed_mw_kg_per_kmol, 6),
            "Density used [kg/m3]": _fmt(result.combined_density_kg_m3, 6),
        },
    ]
    st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

    comp_df = pd.DataFrame(
        [
            {"Component": comp, "Mol %": value}
            for comp, value in result.composition_mol_percent.items()
            if value > 0.0
        ]
    )
    if not comp_df.empty:
        comp_df = comp_df.sort_values("Mol %", ascending=False).reset_index(drop=True)
    st.dataframe(comp_df, width="stretch", hide_index=True)

    csv_text = composition_to_csv(result.composition_mol_percent)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Download mixed composition (CSV)",
            data=csv_text.encode("utf-8"),
            file_name=f"{result.label.replace(':', '').replace(' ', '_')}.csv",
            mime="text/csv",
            key=f"{key_prefix}_dl_csv",
        )
    with col2:
        render_temporary_save_button(
            key=f"{key_prefix}_save",
            canonical_csv_provider=lambda text=csv_text: text,
            format_family=FORMAT_AGA8,
            source_module="mix",
            source_context=result.label,
            base_name_provider=lambda lbl=result.label: lbl,
        )


def _parse_custom_ratios(text: str) -> list[float] | None:
    try:
        values = np.array([float(v.strip()) for v in text.replace(",", " ").split() if v.strip()], dtype=float)
    except ValueError:
        st.error("Could not parse ratio list. Use numbers separated by commas or spaces.")
        return None

    if values.size == 0:
        return None
    if np.any((values < 0.0) | (values > 100.0)):
        st.error("All ratio values must be between 0 and 100.")
        return None

    return np.unique(values).round(6).tolist()


def _render_single_mix(active_composition: dict[str, float]) -> None:
    selected = _render_fluid_selectors(active_composition)
    if selected is None:
        return

    fluid1_name, comp1, fluid2_name, comp2 = selected

    st.divider()
    basis, params = _render_basis_controls("mix_single")

    label1, label2 = _SINGLE_LABELS[basis]
    c1, c2 = st.columns(2)
    with c1:
        amount1 = st.number_input(label1, min_value=0.0, value=70.0, step=1.0, key="mix_single_amount1")
    with c2:
        amount2 = st.number_input(label2, min_value=0.0, value=30.0, step=1.0, key="mix_single_amount2")

    st.divider()
    if st.button("Run mix", type="primary", key="mix_single_run"):
        if amount1 <= 0 and amount2 <= 0:
            st.error("At least one fluid amount must be greater than zero.")
        else:
            try:
                st.session_state[_SINGLE_STATE_KEY] = mix_two(
                    comp1,
                    comp2,
                    fluid1_name=fluid1_name,
                    fluid2_name=fluid2_name,
                    basis=basis,
                    amount1=amount1,
                    amount2=amount2,
                    **params,
                )
            except Exception as exc:
                st.error(f"Mixing failed: {exc}")

    result = st.session_state.get(_SINGLE_STATE_KEY)
    if result is not None:
        st.divider()
        _render_mix_result(result, key_prefix="mix_single_result")


def _render_range_mix(active_composition: dict[str, float]) -> None:
    selected = _render_fluid_selectors(active_composition)
    if selected is None:
        return

    fluid1_name, comp1, fluid2_name, comp2 = selected

    st.divider()
    basis, params = _render_basis_controls("mix_range")

    st.markdown("**Fluid 1 mixing ratios (%)**")
    mode = st.radio(
        "Ratio input mode",
        options=["Range (start / stop / step)", "Custom list"],
        horizontal=True,
        key="mix_range_ratio_mode",
        label_visibility="collapsed",
    )

    ratios: list[float] | None = None
    if mode == "Range (start / stop / step)":
        c1, c2, c3 = st.columns(3)
        with c1:
            start = st.number_input("Start [%]", min_value=0.0, max_value=100.0, value=0.0, step=5.0, key="mix_range_start")
        with c2:
            stop = st.number_input("Stop [%]", min_value=0.0, max_value=100.0, value=100.0, step=5.0, key="mix_range_stop")
        with c3:
            step = st.number_input("Step [%]", min_value=0.1, max_value=100.0, value=10.0, step=1.0, key="mix_range_step")

        if start >= stop:
            st.warning("Start must be lower than Stop.")
        else:
            ratios = np.arange(start, stop + 0.5 * step, step, dtype=float)
            ratios = np.clip(ratios, 0.0, 100.0)
            ratios = np.unique(np.round(ratios, 6)).tolist()
            st.caption(f"{len(ratios)} mix point(s): {ratios}")
    else:
        raw = st.text_input(
            "Enter percentages (comma or space separated)",
            value="0, 25, 50, 75, 100",
            key="mix_range_custom",
        )
        ratios = _parse_custom_ratios(raw)
        if ratios is not None:
            st.caption(f"{len(ratios)} mix point(s): {ratios}")

    total_amount = 100.0
    if basis in ("volume", "std_volume"):
        total_amount = st.number_input(
            _TOTAL_LABELS[basis],
            min_value=0.01,
            value=100.0,
            step=1.0,
            key="mix_range_total_amount",
        )

    st.divider()
    if st.button("Run range mix", type="primary", key="mix_range_run"):
        if not ratios:
            st.error("Define at least one ratio value.")
        else:
            try:
                st.session_state[_RANGE_STATE_KEY] = mix_range(
                    comp1,
                    comp2,
                    fluid1_name=fluid1_name,
                    fluid2_name=fluid2_name,
                    basis=basis,
                    ratios_percent=ratios,
                    total_amount=total_amount,
                    **params,
                )
            except Exception as exc:
                st.error(f"Range mix failed: {exc}")

    results: list[MixResult] = st.session_state.get(_RANGE_STATE_KEY, [])
    if results:
        st.divider()

        summary = []
        for r in results:
            summary.append(
                {
                    "Label": r.label,
                    f"{r.fluid1_name} fraction": round(r.ratio_fluid1, 6),
                    f"{r.fluid2_name} fraction": round(1.0 - r.ratio_fluid1, 6),
                    "Mixed MW [kg/kmol]": round(r.mixed_mw_kg_per_kmol, 6),
                }
            )
        st.dataframe(pd.DataFrame(summary), width="stretch", hide_index=True)

        bulk_rows = []
        for r in results:
            for comp, val in r.composition_mol_percent.items():
                bulk_rows.append(
                    {
                        "Mix label": r.label,
                        "Component": comp,
                        "Mol %": val,
                    }
                )

        st.download_button(
            "Download all range results (CSV)",
            data=pd.DataFrame(bulk_rows).to_csv(index=False).encode("utf-8"),
            file_name="mix_range_results.csv",
            mime="text/csv",
            key="mix_range_bulk_download",
        )

        for idx, result in enumerate(results):
            with st.expander(result.label):
                _render_mix_result(result, key_prefix=f"mix_range_result_{idx}")


def render(composition: dict | None) -> None:
    st.subheader("Mix")
    st.caption(
        "Mix two AGA8 fluids by mass, mole, volume, or standard volume. "
        "Calculations are NumPy-based for fast single and range mixing."
    )

    if composition is None:
        st.info("Enter a valid composition in the main table first.")
        return

    tab_single, tab_range = st.tabs(["Single Mix", "Range Mix"])
    with tab_single:
        _render_single_mix(composition)
    with tab_range:
        _render_range_mix(composition)
