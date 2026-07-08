"""
AGA8 vs REFPROP tab — results from Global Flow Measurement Workshop 2026 paper.

Interactive viewer for pre-computed GERG-2008 and DETAIL relative deviations against a
REFPROP reference across a pressure sweep, for 50 anonymized natural-gas metering stations
(gasmet_01 … gasmet_50). REFPROP is not run in-app; all results are static.

Stations can be filtered by AGA8 quality range:
- Pipeline Quality (DETAIL applicability)
- Intermediate Quality (GERG-2008 applicability, outside pipeline quality)
- Outside Intermediate Quality (outside GERG-2008 applicability)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from utils.session_fluids import FORMAT_AGA8
from utils.session_fluids_ui import render_temporary_save_button

from ..composition_input import export_composition_values_to_canonical_csv
from ..validation import validate_composition

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "aga8_vs_refprop"
METADATA_FILE = DATA_DIR / "metadata.json"
RESULTS_DIR = DATA_DIR / "results"

EOS_OPTIONS = ["GERG-2008", "DETAIL"]
QUALITY_GROUPS = ["Pipeline Quality", "Intermediate Quality", "Outside Intermediate Quality"]
# Composite filters map a UI label to the set of quality groups it selects.
COMPOSITE_FILTERS = {
    "Outside Pipeline Quality Range": ("Intermediate Quality", "Outside Intermediate Quality"),
}
GROUP_FILTER_OPTIONS = ["All quality ranges", *QUALITY_GROUPS, *COMPOSITE_FILTERS]

GERG_COLOR = "#0000a2"
DETAIL_COLOR = "#E69F00"

COMPONENT_ORDER = [
    "N2", "CO2", "C1", "C2", "C3", "iC4", "nC4", "iC5", "nC5",
    "nC6", "nC7", "nC8", "nC9", "nC10",
]
C6_PLUS_COMPONENTS = ["nC6", "nC7", "nC8", "nC9", "nC10"]

_METRICS = [
    ("Mass Density", "GERG_rho_rel_dev", "DETAIL_rho_rel_dev"),
    ("Speed of sound", "GERG_w_rel_dev", "DETAIL_w_rel_dev"),
    ("Compressibility factor", "GERG_Z_rel_dev", "DETAIL_Z_rel_dev"),
    ("Isentropic exponent", "GERG_kappa_rel_dev", "DETAIL_kappa_rel_dev"),
]
_AXIS_POSITIONS = [(1, 1), (1, 2), (2, 1), (2, 2)]


def _is_klab_gas(gas_id: str) -> bool:
    return gas_id.startswith("klab_gas_")


def _force_fixed_y_axis_for_klab() -> None:
    if st.session_state.get("aga8_refprop_include_klab", False):
        st.session_state["aga8_refprop_fix_y"] = True
        st.session_state["aga8_refprop_ymin"] = -1.3
        st.session_state["aga8_refprop_ymax"] = 1.3


def component_violations(composition: dict[str, float], mode: str) -> int:
    """Count component-range violations for a composition using the built-in AGA8 limits.

    Uses gasprops' own ``validate_composition`` (the same limits as the AGA8 Validation tab),
    so pipeline/intermediate classification stays consistent with the rest of the app. The
    composition-total check is excluded — only component/group range violations are counted.
    """
    issues = validate_composition(composition, mode)
    return sum(1 for issue in issues if issue.name != "TOTAL")


def classify_quality(detail_violations: int, gerg_violations: int) -> str:
    """Map DETAIL/GERG component-violation counts to an AGA8 quality range."""
    if detail_violations == 0:
        return "Pipeline Quality"
    if gerg_violations == 0:
        return "Intermediate Quality"
    return "Outside Intermediate Quality"


def load_metadata() -> pd.DataFrame:
    """Load anonymized station metadata as a DataFrame sorted by station id.

    Violation counts and the quality-range classification are computed on the fly from the
    stored composition via the gasprops built-in validation, so they always reflect the
    app's single source of truth rather than any pre-stored value.
    """
    if not METADATA_FILE.exists():
        raise FileNotFoundError(f"Metadata not found: {METADATA_FILE}")
    with open(METADATA_FILE, "r", encoding="utf-8") as fh:
        metadata = json.load(fh)
    rows = []
    for entry in metadata.values():
        composition = entry["composition"]
        detail_violations = component_violations(composition, "DETAIL")
        gerg_violations = component_violations(composition, "GERG-2008")
        rows.append(
            {
                "id": entry["id"],
                "data_source": entry.get("data_source", "Norwegian gas grid"),
                "quality_group": classify_quality(detail_violations, gerg_violations),
                "temperature_c": entry.get("temperature_c"),
                "cricondentherm": entry.get("cricondentherm"),
                "detail_violations": detail_violations,
                "gerg_violations": gerg_violations,
            }
        )
    return pd.DataFrame(rows).sort_values("id").reset_index(drop=True)


@lru_cache(maxsize=None)
def _load_compositions() -> dict[str, dict[str, float]]:
    with open(METADATA_FILE, "r", encoding="utf-8") as fh:
        metadata = json.load(fh)
    return {entry["id"]: entry["composition"] for entry in metadata.values()}


@st.cache_data(show_spinner=False)
def load_results(station_id: str) -> pd.DataFrame:
    """Load the pressure-sweep result table for a single anonymized station."""
    csv_path = RESULTS_DIR / f"{station_id}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Results not found for {station_id}: {csv_path}")
    return pd.read_csv(csv_path)


@st.cache_data(show_spinner=False)
def load_all_results() -> dict[str, pd.DataFrame]:
    """Load all pressure-sweep result tables in one cached operation."""
    return {csv_path.stem: pd.read_csv(csv_path) for csv_path in sorted(RESULTS_DIR.glob("*.csv"))}


def _apply_axis_styling(figure: go.Figure, y_axis_range) -> go.Figure:
    figure.update_xaxes(
        title_text="Pressure [bara]",
        showgrid=True,
        gridcolor="rgba(120, 120, 120, 0.30)",
        zeroline=False,
        tickmode="linear",
        dtick=25,
    )
    figure.update_yaxes(
        title_text="Relative deviation [%]",
        showgrid=True,
        gridcolor="rgba(120, 120, 120, 0.30)",
        zeroline=True,
        zerolinecolor="rgba(80, 80, 80, 0.45)",
    )
    if y_axis_range is not None:
        figure.update_yaxes(range=y_axis_range)
    else:
        figure.update_yaxes(autorange=True)
    return figure


def _create_single_figure(station_id, df, eos_models, y_axis_range, eos_colors) -> go.Figure:
    trace_map = {
        "GERG-2008": {"color": eos_colors["GERG-2008"], "gerg": True},
        "DETAIL": {"color": eos_colors["DETAIL"], "gerg": False},
    }
    figure = make_subplots(rows=2, cols=2, subplot_titles=[m[0] for m in _METRICS])

    for eos_name in eos_models:
        is_gerg = trace_map[eos_name]["gerg"]
        for index, (_, gerg_col, detail_col) in enumerate(_METRICS):
            row, col = _AXIS_POSITIONS[index]
            column_name = gerg_col if is_gerg else detail_col
            figure.add_trace(
                go.Scatter(
                    x=df["P_bara"],
                    y=df[column_name],
                    mode="lines+markers",
                    name=eos_name,
                    legendgroup=eos_name,
                    showlegend=index == 0,
                    line={"color": trace_map[eos_name]["color"]},
                    marker={"size": 7},
                ),
                row=row,
                col=col,
            )

    figure.update_layout(
        title=f"{station_id} — all pressure points",
        height=850,
        template="plotly_white",
    )
    return _apply_axis_styling(figure, y_axis_range)


def _create_group_figure(results_by_station, eos_models, title_label, y_axis_range, eos_colors) -> go.Figure:
    figure = make_subplots(rows=2, cols=2, subplot_titles=[m[0] for m in _METRICS])

    trace_specs = {
        "GERG-2008": {
            "column_index": 1,
            "line": {"color": eos_colors["GERG-2008"], "dash": "solid"},
            "marker": {"size": 5},
        },
        "DETAIL": {
            "column_index": 2,
            "line": {"color": eos_colors["DETAIL"], "dash": "dash"},
            "marker": {"size": 5, "symbol": "square"},
        },
    }

    for index, (_, gerg_col, detail_col) in enumerate(_METRICS):
        row, col = _AXIS_POSITIONS[index]
        metric_columns = {"GERG-2008": gerg_col, "DETAIL": detail_col}

        for eos_name in eos_models:
            x_values = []
            y_values = []
            gas_ids = []
            for station_id, df in results_by_station.items():
                point_count = len(df)
                x_values.extend(df["P_bara"].tolist())
                y_values.extend(df[metric_columns[eos_name]].tolist())
                gas_ids.extend([station_id] * point_count)
                x_values.append(None)
                y_values.append(None)
                gas_ids.append(None)

            figure.add_trace(
                go.Scatter(
                    x=x_values,
                    y=y_values,
                    customdata=gas_ids,
                    mode="lines+markers",
                    name=eos_name,
                    legendgroup=eos_name,
                    showlegend=index == 0,
                    line=trace_specs[eos_name]["line"],
                    marker=trace_specs[eos_name]["marker"],
                    hovertemplate=(
                        "Gas: %{customdata}<br>"
                        f"EOS: {eos_name}<br>"
                        "Pressure: %{x:.1f} bara<br>"
                        "Relative deviation: %{y:.4f}%<extra></extra>"
                    ),
                ),
                row=row,
                col=col,
            )

    figure.update_layout(title=title_label, height=900, template="plotly_white")
    return _apply_axis_styling(figure, y_axis_range)


def _composition_dataframe(station_id: str) -> pd.DataFrame:
    composition = _load_compositions()[station_id]
    rows = [
        {"Component": component, "Mol %": composition[component]}
        for component in COMPONENT_ORDER
        if component in composition
    ]
    return pd.DataFrame(rows)


def _composition_wide_dataframe(gas_ids: list[str]) -> pd.DataFrame:
    compositions = _load_compositions()
    rows = []
    for component in COMPONENT_ORDER:
        row = {"Component": component}
        for gas_id in gas_ids:
            row[gas_id] = float(compositions[gas_id].get(component, 0.0))
        rows.append(row)
    c6_plus_row = {"Component": "C6+ (nC6…nC10)"}
    for gas_id in gas_ids:
        c6_plus_row[gas_id] = sum(
            float(compositions[gas_id].get(component, 0.0)) for component in C6_PLUS_COMPONENTS
        )
    rows.append(c6_plus_row)
    return pd.DataFrame(rows)


def _c6_plus_mol_pct(station_id: str) -> float:
    composition = _load_compositions()[station_id]
    return sum(float(composition.get(component, 0.0)) for component in C6_PLUS_COMPONENTS)


def render(composition: dict | None) -> None:
    """Render the AGA8 vs REFPROP viewer."""
    st.subheader("AGA8 vs REFPROP — results from Global Flow Measurement Workshop 2026 paper")
    st.markdown(
        """
The results in this tab originate from the paper **"Uncertainty in Calculated Gas Properties
Outside Pipeline Quality Natural Gas"**, presented at the **Global Flow Measurement Workshop (GFMW)
2026**.

This tab shows pre-computed comparisons for 50 anonymized gas metering stations connected to
the Norwegian gas grid (`gasmet_01`–`gasmet_50`) and three anonymized K-lab gases
(`klab_gas_01`–`klab_gas_03`). In the source data for the gas metering stations, gas
compositions were measured up to **C6+**. For the calculations shown here, the reported C6+
fraction was distributed into **nC6–nC10** using a fixed split: **nC6 50.0%, nC7 30.0%,
nC8 12.5%, nC9 5.0%, and nC10 2.5%**.

In addition, three K-lab gases are included in the results. The K-lab gases originate from the gas metering station at the K-lab VGII multiphase flow loop,
as presented in the paper. They typically contain higher C5+ content than most of the
`gasmet` gases, and might be more representative of gases found closer to the wells, for example at
first-stage and test separators. To include the K-lab gases in the plots, check the **Include K-lab gases** checkbox.

For each composition, AGA8 DETAIL and AGA8 GERG-2008 properties were calculated with `pvtlib` and
compared against REFPROP reference results obtained through `ctREFPROP`. REFPROP requires a
separate license and is not run in this app.

Cricondentherm values were calculated with NeqSim, and each pressure sweep was evaluated from
10 to 300 bara at `max(cricondentherm + 10 °C, 10 °C)`. The plots show relative deviation from
REFPROP in percent.
        """
    )
    with st.expander("Calculation method and data source", expanded=False):
        st.markdown(
            """
This tab presents pre-computed property comparisons for 50 anonymized gas metering stations
connected to the Norwegian gas grid and three K-lab gases. The metering-station
identities have been removed and replaced by neutral identifiers (`gasmet_01`–`gasmet_50`), and
the selected K-lab gases are identified only as `klab_gas_01`–`klab_gas_03`. The data are made
available for this study with permission, but no field, station, or sample names are included in
the public app.

The source compositions for the gas metering stations were measured up to **C6+**. In this
study, the reported C6+ fraction was distributed into **nC6–nC10** using the fixed split from
the paper:

| Component | Fraction of C6+ |
|---|---:|
| nC6 | 50.0% |
| nC7 | 30.0% |
| nC8 | 12.5% |
| nC9 | 5.0% |
| nC10 | 2.5% |

The three K-lab gases originate from the gas metering station at the K-lab VGII multiphase flow
loop. They typically contain higher C5+ content than most of the `gasmet` gases, and are included
as representative examples of richer gases found closer to the wells, for example at first-stage
and test separators.

For each gas composition, the cricondentherm was calculated with NeqSim, and the analysis
temperature was set to the cricondentherm plus 10 °C, with a minimum temperature of 10 °C.
Gas properties were then calculated from 10 to 300 bara.

The plots compare properties calculated with AGA8 DETAIL and AGA8 GERG-2008 against REFPROP. DETAIL
and GERG-2008 were calculated using `pvtlib`, while REFPROP was accessed programmatically using
the `ctREFPROP` Python package. REFPROP itself requires a separate license and is not run inside
this app; only the pre-computed REFPROP comparison results are included here.

Relative deviations are shown as:

`100 × (Property_AGA8 - Property_REFPROP) / Property_REFPROP [%]`
            """
        )

    try:
        metadata_df = load_metadata()
    except FileNotFoundError as error:
        st.error(str(error))
        return

    control_col_1, control_col_2 = st.columns(2)
    with control_col_1:
        include_klab = st.checkbox(
            "Include K-lab gases",
            value=False,
            key="aga8_refprop_include_klab",
            on_change=_force_fixed_y_axis_for_klab,
            help=(
                "Include three K-lab VGII gases selected to represent low, "
                "medium, and high DETAIL density deviations."
            ),
        )
        view_mode = st.radio(
            "View mode",
            ["Grouped gases", "Single gas"],
            index=0,
            key="aga8_refprop_view_mode",
        )
        quality_filter = st.selectbox(
            "Quality range filter",
            GROUP_FILTER_OPTIONS,
            key="aga8_refprop_quality_filter",
        )

    plot_metadata_df = metadata_df.copy()
    if not include_klab:
        plot_metadata_df = plot_metadata_df[~plot_metadata_df["id"].map(_is_klab_gas)]
    else:
        _force_fixed_y_axis_for_klab()

    group_counts = plot_metadata_df["quality_group"].value_counts()
    metric_cols = st.columns(4)
    metric_cols[0].metric("Gases", len(plot_metadata_df))
    metric_cols[1].metric("Pipeline Quality", int(group_counts.get("Pipeline Quality", 0)))
    metric_cols[2].metric("Intermediate Quality", int(group_counts.get("Intermediate Quality", 0)))
    metric_cols[3].metric(
        "Outside Intermediate", int(group_counts.get("Outside Intermediate Quality", 0))
    )
    with control_col_2:
        eos_models = st.multiselect(
            "EOS models",
            EOS_OPTIONS,
            default=EOS_OPTIONS,
            key="aga8_refprop_eos",
        )
        gerg_color_col, detail_color_col = st.columns(2)
        gerg_color = gerg_color_col.color_picker(
            "GERG color",
            value=GERG_COLOR,
            key="aga8_refprop_gerg_color",
        )
        detail_color = detail_color_col.color_picker(
            "DETAIL color",
            value=DETAIL_COLOR,
            key="aga8_refprop_detail_color",
        )
        use_default_y_range = st.checkbox(
            "Fix y-axis range for deviation plots",
            value=True,
            key="aga8_refprop_fix_y",
        )
        if use_default_y_range:
            y_min_col, y_max_col = st.columns(2)
            y_axis_min = y_min_col.number_input(
                "Y-axis min", value=-0.6, step=0.1, format="%.2f", key="aga8_refprop_ymin"
            )
            y_axis_max = y_max_col.number_input(
                "Y-axis max", value=0.6, step=0.1, format="%.2f", key="aga8_refprop_ymax"
            )

    if not eos_models:
        st.warning("Select at least one EOS model.")
        return

    eos_colors = {
        "GERG-2008": gerg_color,
        "DETAIL": detail_color,
    }

    y_axis_range = None
    if use_default_y_range:
        y_axis_range = [min(y_axis_min, y_axis_max), max(y_axis_min, y_axis_max)]

    filtered_df = plot_metadata_df
    if quality_filter in COMPOSITE_FILTERS:
        filtered_df = plot_metadata_df[plot_metadata_df["quality_group"].isin(COMPOSITE_FILTERS[quality_filter])]
    elif quality_filter != "All quality ranges":
        filtered_df = plot_metadata_df[plot_metadata_df["quality_group"] == quality_filter]

    available_ids = filtered_df["id"].tolist()
    if not available_ids:
        st.info("No gases available for the selected quality range.")
        return

    composition_table_ids = available_ids
    if view_mode == "Single gas":
        selected_id = st.selectbox(
            "Gas", available_ids, key=f"aga8_refprop_single_id_{quality_filter}_{include_klab}"
        )
        selected_meta = filtered_df[filtered_df["id"] == selected_id].iloc[0]
        st.write(f"**Quality range:** {selected_meta['quality_group']}")
        detail_col, gerg_col = st.columns(2)
        detail_col.write(f"**DETAIL violations:** {selected_meta['detail_violations']}")
        gerg_col.write(f"**GERG violations:** {selected_meta['gerg_violations']}")

        results_df = load_results(selected_id)
        st.plotly_chart(
            _create_single_figure(selected_id, results_df, eos_models, y_axis_range, eos_colors),
            use_container_width=True,
        )
        with st.expander("Show result data"):
            st.dataframe(results_df, use_container_width=True)
    else:
        selected_ids = st.multiselect(
            "Gases",
            available_ids,
            default=available_ids,
            key=f"aga8_refprop_group_ids_{quality_filter}_{include_klab}",
        )
        composition_table_ids = selected_ids
        st.write(f"Showing **{len(selected_ids)}** gases.")
        if not selected_ids:
            st.info("Select at least one gas.")
        else:
            all_results = load_all_results()
            results_by_station = {station_id: all_results[station_id] for station_id in selected_ids}
            st.plotly_chart(
                _create_group_figure(results_by_station, eos_models, quality_filter, y_axis_range, eos_colors),
                use_container_width=True,
            )
            with st.expander("Show gas summary"):
                st.dataframe(
                    filtered_df[filtered_df["id"].isin(selected_ids)],
                    use_container_width=True,
                    hide_index=True,
                )

    st.divider()
    st.markdown("#### Gas composition")
    show_wide_composition_table = st.toggle(
        "Show compositions in one table",
        value=False,
        key=f"aga8_refprop_composition_wide_{quality_filter}_{include_klab}_{view_mode}",
        help="Show components as rows and one column per gas for the current filter/selection.",
    )

    if show_wide_composition_table:
        if not composition_table_ids:
            st.info("Select at least one gas to show the composition table.")
        else:
            st.caption(
                "Wide composition table for the current gas filter/selection. Values are mol %."
            )
            st.dataframe(
                _composition_wide_dataframe(composition_table_ids),
                use_container_width=True,
                hide_index=True,
            )
    else:
        composition_options = composition_table_ids or plot_metadata_df["id"].tolist()
        composition_id = st.selectbox(
            "Select gas",
            composition_options,
            key=f"aga8_refprop_composition_id_{include_klab}_{quality_filter}_{view_mode}",
        )
        st.dataframe(_composition_dataframe(composition_id), use_container_width=True, hide_index=True)
        st.metric("C6+ (nC6…nC10)", f"{_c6_plus_mol_pct(composition_id):.4f} mol %")

        selected_composition = _load_compositions()[composition_id]
        render_temporary_save_button(
            key="aga8_refprop_session_save",
            canonical_csv_provider=lambda: export_composition_values_to_canonical_csv(
                selected_composition
            ),
            format_family=FORMAT_AGA8,
            source_module="aga8_vs_refprop",
            base_name_provider=lambda: composition_id,
            help_text=(
                "Save this gas composition as a temporary session fluid so it can be "
                "reused in other tabs (e.g. Mix). Kept only in memory for this browser session."
            ),
        )
