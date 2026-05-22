"""
Shared composition input helper for the Gas Properties module.

Provides two functions:
  composition_io_controls(key_prefix) -- import/export controls (left column)
  composition_input(key_prefix)       -- editable table          (right column)

Call composition_io_controls() BEFORE composition_input() so that any
imported values are already in session state when the table renders.
"""

from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
import io
import os
from typing import IO

import pandas as pd
import streamlit as st

from utils.composition_csv import (
    canonicalize_composition_dataframe,
    export_canonical_composition_csv,
    handle_lossy_heavy_component_conversion,
)
from utils.session_fluids import (
    FORMAT_AGA8,
    convert_pvtcalc_to_aga8,
    format_aga8_conversion_warning,
)
from utils.session_fluids_ui import (
    render_load_saved_fluid_selector,
    render_temporary_save_button,
)

_COMPOSITIONS_DIR = Path(__file__).resolve().parents[2] / "data" / "examples"

STD_COMPONENTS: dict[str, str] = {
    "N2":   "Nitrogen",
    "CO2":  "Carbon dioxide",
    "C1":   "Methane",
    "C2":   "Ethane",
    "C3":   "Propane",
    "iC4":  "Isobutane",
    "nC4":  "n-Butane",
    "iC5":  "Isopentane",
    "nC5":  "n-Pentane",
    "nC6":  "Hexane",
    "nC7":  "Heptane",
    "nC8":  "Octane",
    "nC9":  "Nonane",
    "nC10": "Decane",
}

EXTRA_COMPONENTS: dict[str, str] = {
    "H2O": "Water",
    "He":  "Helium",
    "H2":  "Hydrogen",
    "Ar":  "Argon",
    "CO":  "Carbon monoxide",
    "O2":  "Oxygen",
    "H2S": "Hydrogen sulphide",
}

COMPONENTS: dict[str, str] = {**STD_COMPONENTS, **EXTRA_COMPONENTS}

_DEFAULTS: dict[str, float] = {"C1": 100.0}

from .domain import COMPONENTS as _COMP_SPECS

_FALLBACK_COMPONENT_MW: dict[str, float] = {k: spec.mw_g_mol for k, spec in _COMP_SPECS.items()}


@lru_cache(maxsize=1)
def _aga8_component_molecular_weights() -> dict[str, float]:
    """Return AGA8 molecular weights, using fallback values if needed."""
    try:
        import pvtlib

        aga8 = pvtlib.AGA8("GERG-2008")
        return {
            component: float(aga8.molecular_weights[aga8.component_indices[component]])
            for component in COMPONENTS
        }
    except Exception:
        return dict(_FALLBACK_COMPONENT_MW)


def load_composition_values_from_csv(
    source: str | os.PathLike[str] | IO[str] | IO[bytes],
    *,
    require_full_schema: bool = False,
) -> tuple[dict[str, float], list[str], list[str]]:
    """Load composition values from a CSV source."""
    composition_df = canonicalize_composition_dataframe(
        source,
        required_columns=("Component", "MolePercent"),
        heavy_component_names="keep",
    )
    composition_df, lossy_warnings = handle_lossy_heavy_component_conversion(
        composition_df,
        target="defined",
        sum_columns=("MolePercent",),
    )
    imported = dict(zip(composition_df["Component"], composition_df["MolePercent"]))
    unknown = [component for component in imported if component not in COMPONENTS]
    values = {component: float(imported.get(component, 0.0)) for component in COMPONENTS}
    return values, unknown, lossy_warnings


def normalize_composition_values(values: dict[str, float]) -> dict[str, float]:
    """Normalize values so they sum to 100 mol%."""
    total = sum(values.values())
    if total <= 0.0:
        return dict(values)
    return {component: value / total * 100.0 for component, value in values.items()}


def export_composition_values_to_canonical_csv(values: dict[str, float]) -> str:
    """Export composition values to canonical CSV text."""
    component_mw = _aga8_component_molecular_weights()
    export_df = pd.DataFrame(
        {
            "Component": list(COMPONENTS.keys()),
            "MolePercent": [float(values.get(component, 0.0)) for component in COMPONENTS],
            "MW": [component_mw[component] for component in COMPONENTS],
            "Dens": [None for _ in COMPONENTS],
        }
    )
    return export_canonical_composition_csv(export_df, heavy_component_names="defined")


_EDITABLE_SOURCE = "editable"
_EXAMPLE_SOURCE = "example"


def _replace_composition_values(
    key_prefix: str,
    values: dict[str, float],
    *,
    source: str = _EDITABLE_SOURCE,
) -> None:
    """Replace stored composition values in session state."""
    session_key = _ss_key(key_prefix, source=source)
    st.session_state[session_key] = values
    editor_key = _table_key(key_prefix, source)
    if editor_key in st.session_state:
        del st.session_state[editor_key]


def _set_zero_composition_values(key_prefix: str) -> None:
    """Set all stored composition values to zero."""
    _replace_composition_values(
        key_prefix,
        {component: 0.0 for component in COMPONENTS},
        source=_EDITABLE_SOURCE,
    )


def _normalize_current_composition_values(key_prefix: str, values: dict[str, float]) -> None:
    """Normalize the current stored composition values."""
    _replace_composition_values(
        key_prefix,
        normalize_composition_values(values),
        source=_EDITABLE_SOURCE,
    )


def _ss_key(key_prefix: str, *, source: str = _EDITABLE_SOURCE) -> str:
    """Build the session-state key for composition values."""
    return f"{key_prefix}_{source}_comp_values"


def _table_key(key_prefix: str, source: str) -> str:
    """Build the table widget key for a composition source."""
    return f"{key_prefix}_{source}_table"


def _use_examples_key(key_prefix: str) -> str:
    """Build the session-state key for the example toggle."""
    return f"{key_prefix}_use_example_gases"


def _editable_import_applied_key(key_prefix: str) -> str:
    """Build the session-state key for the imported-file marker."""
    return f"{key_prefix}_editable_import_applied"


def _editable_import_counter_key(key_prefix: str) -> str:
    """Build the session-state key for the import counter."""
    return f"{key_prefix}_editable_import_counter"


def _example_selection_key(key_prefix: str) -> str:
    """Build the session-state key for the example selector."""
    return f"{key_prefix}_example_selection"


def _loaded_example_key(key_prefix: str) -> str:
    """Build the session-state key for the loaded example marker."""
    return f"{key_prefix}_loaded_example"


def _active_source(key_prefix: str) -> str:
    """Return the active composition source name."""
    if st.session_state.get(_use_examples_key(key_prefix), False):
        return _EXAMPLE_SOURCE
    return _EDITABLE_SOURCE


def _active_values(key_prefix: str) -> dict[str, float]:
    """Return the active composition values from session state."""
    return dict(st.session_state[_ss_key(key_prefix, source=_active_source(key_prefix))])


def _init_session_state(key_prefix: str) -> None:
    """Initialize composition-related session state values."""
    defaults = {comp: _DEFAULTS.get(comp, 0.0) for comp in COMPONENTS}
    for source in (_EDITABLE_SOURCE, _EXAMPLE_SOURCE):
        session_key = _ss_key(key_prefix, source=source)
        if session_key not in st.session_state:
            st.session_state[session_key] = dict(defaults)


def _available_example_paths() -> dict[str, str]:
    """Return the available example composition file paths."""
    example_dir = os.path.normpath(str(_COMPOSITIONS_DIR))
    if not os.path.isdir(example_dir):
        return {}
    filenames = {filename for filename in os.listdir(example_dir) if filename.endswith(".csv")}
    preferred_order = [
        "lean_gas.csv",
        "rich_gas_01.csv",
        "rich_gas_02.csv",
        "rich_gas_03.csv",
        "rich_gas_04.csv",
    ]
    ordered_filenames = [name for name in preferred_order if name in filenames]
    ordered_filenames.extend(sorted(filenames - set(ordered_filenames)))
    return OrderedDict(
        (
            os.path.splitext(filename)[0].replace("_", " ").title(),
            os.path.join(example_dir, filename),
        )
        for filename in ordered_filenames
    )


def _load_example_composition(key_prefix: str, example_name: str, example_path: str) -> None:
    """Load an example composition into session state."""
    new_values, unknown, lossy_warnings = load_composition_values_from_csv(example_path)
    _replace_composition_values(
        key_prefix,
        new_values,
        source=_EXAMPLE_SOURCE,
    )
    for warning in lossy_warnings:
        st.warning(warning)
    if unknown:
        st.warning(f"Ignored unknown components: {', '.join(unknown)}")
    st.session_state[_loaded_example_key(key_prefix)] = example_name


def composition_io_controls(key_prefix: str = "comp", show_examples: bool = True) -> None:
    """Render composition import and export controls."""
    _init_session_state(key_prefix)

    st.markdown("**Composition file**")

    example_paths = _available_example_paths()
    use_examples_key = _use_examples_key(key_prefix)
    use_examples = False
    if show_examples and example_paths:
        use_examples = st.toggle(
            "Use example gases",
            value=st.session_state.get(use_examples_key, False),
            key=use_examples_key,
            help="Turn on to use a read-only example composition instead of your editable/imported gas.",
        )
        if use_examples:
            example_names = list(example_paths)
            current_example = st.session_state.get(_example_selection_key(key_prefix), example_names[0])
            if current_example not in example_paths:
                current_example = example_names[0]
            selected_example = st.selectbox(
                "Example gas",
                options=example_names,
                index=example_names.index(current_example),
                key=_example_selection_key(key_prefix),
            )
            if st.session_state.get(_loaded_example_key(key_prefix)) != selected_example:
                try:
                    _load_example_composition(
                        key_prefix,
                        selected_example,
                        example_paths[selected_example],
                    )
                except Exception as exc:
                    st.error(f"Could not load example: {exc}")
    else:
        st.session_state[use_examples_key] = False

    st.divider()

    export_cols = st.columns(2)
    export_cols[0].download_button(
        label="Export composition (CSV)",
        data=export_composition_values_to_canonical_csv(_active_values(key_prefix)).encode(),
        file_name="composition.csv",
        mime="text/csv",
        key=f"{key_prefix}_export_csv",
        help=(
            "Exports an AGA8 composition CSV using the shared headers "
            "Component,MolePercent,MW,Dens. MW comes from AGA8; Dens is left empty."
        ),
    )
    current_values = _active_values(key_prefix)
    composition_is_empty = sum(current_values.values()) == 0.0
    with export_cols[1]:
        render_temporary_save_button(
            key=f"{key_prefix}_session_save",
            canonical_csv_provider=lambda: export_composition_values_to_canonical_csv(
                _active_values(key_prefix)
            ),
            format_family=FORMAT_AGA8,
            source_module="gas_properties",
            base_name_provider=lambda: "Gas Properties composition",
            disabled=composition_is_empty,
        )

    if use_examples:
        st.caption("Example compositions are read-only. Turn off **Use example gases** to import or edit a composition.")
    else:
        applied_key = _editable_import_applied_key(key_prefix)
        counter_key = _editable_import_counter_key(key_prefix)
        if counter_key not in st.session_state:
            st.session_state[counter_key] = 0

        picked_fluid = render_load_saved_fluid_selector(
            key=f"{key_prefix}_session_load",
            format_family=None,
        )
        if picked_fluid is not None:
            try:
                if picked_fluid.format_family == FORMAT_AGA8:
                    csv_text = picked_fluid.canonical_csv
                else:
                    conversion = convert_pvtcalc_to_aga8(picked_fluid.canonical_csv)
                    csv_text = conversion.canonical_csv
                    warning_msg = format_aga8_conversion_warning(conversion)
                    if warning_msg:
                        st.warning(warning_msg)
                new_values, unknown, lossy_warnings = load_composition_values_from_csv(
                    io.StringIO(csv_text)
                )
                for warning in lossy_warnings:
                    st.warning(warning)
                if unknown:
                    st.warning(f"Ignored unknown components: {', '.join(unknown)}")
                _replace_composition_values(
                    key_prefix,
                    new_values,
                    source=_EDITABLE_SOURCE,
                )
                st.session_state[counter_key] += 1
                st.success(f"Loaded saved fluid “{picked_fluid.display_name}”.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load saved fluid: {exc}")

        uploaded = st.file_uploader(
            "Import composition (CSV)",
            type="csv",
            key=f"{key_prefix}_import_csv_{st.session_state[counter_key]}",
            help=(
                "AGA8 composition CSVs use the shared headers Component,MolePercent,MW,Dens, "
                "but gas imports only read Component and MolePercent. "
                "These files are AGA8-specific and are not intended as interchangeable mixture/PVT files."
            ),
        )
        if uploaded is not None:
            file_id = (uploaded.name, uploaded.size)
            if st.session_state.get(applied_key) != file_id:
                try:
                    new_values, unknown, lossy_warnings = load_composition_values_from_csv(uploaded)
                    for warning in lossy_warnings:
                        st.warning(warning)
                    if unknown:
                        st.warning(f"Ignored unknown components: {', '.join(unknown)}")
                    _replace_composition_values(
                        key_prefix,
                        new_values,
                        source=_EDITABLE_SOURCE,
                    )
                    st.session_state[applied_key] = file_id
                    st.session_state[counter_key] += 1
                    st.success("Composition imported.")
                except Exception as exc:
                    st.error(f"Could not read CSV: {exc}")
        else:
            if applied_key in st.session_state:
                del st.session_state[applied_key]


def composition_input(key_prefix: str = "comp") -> dict | None:
    """Render the editable gas composition table."""
    _init_session_state(key_prefix)
    source = _active_source(key_prefix)
    is_example_source = source == _EXAMPLE_SOURCE
    k = _ss_key(key_prefix, source=source)
    active_components = dict(COMPONENTS)

    df = pd.DataFrame({
        "Component": list(active_components.keys()),
        "Name":      list(active_components.values()),
        "Mol %":     [st.session_state[k].get(c, 0.0) for c in active_components],
    })

    edited = st.data_editor(
        df,
        key=_table_key(key_prefix, source),
        width='stretch',
        hide_index=True,
        disabled=is_example_source,
        column_config={
            "Component": st.column_config.TextColumn("Component", disabled=True, width="small"),
            "Name":      st.column_config.TextColumn("Name",      disabled=True, width="medium"),
            "Mol %":     st.column_config.NumberColumn(
                "Mol %",
                min_value=0.0,
                max_value=100.0,
                step=0.0001,
                format="%.4f",
                width="small",
            ),
        },
        num_rows="fixed",
    )

    values: dict[str, float] = dict(st.session_state[k])
    if not is_example_source:
        values.update(zip(edited["Component"], edited["Mol %"]))
        st.session_state[k] = values

        action_cols = st.columns(2)
        if action_cols[0].button("Set to zero", key=f"{key_prefix}_set_zero", help="Set all mole-percent values to zero"):
            _set_zero_composition_values(key_prefix)
            st.rerun()
        if action_cols[1].button("Normalize", key=f"{key_prefix}_normalize", help="Scale mole-percent values to sum to 100"):
            _normalize_current_composition_values(key_prefix, values)
            st.rerun()
    else:
        st.caption("Example compositions are shown read-only.")

    total = sum(values.values())
    if total == 0.0:
        st.error("Total composition is 0 mol%. Enter at least one component.")
        return None

    st.markdown(f"**Total:** {total:.1f} mol%")
    if abs(total - 100.0) > 0.01:
        st.warning("Composition does not sum to 100 % -- will be normalised before calculation.")

    return values
