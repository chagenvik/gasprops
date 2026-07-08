import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gasprop.app import VIEW_MAP
from gasprop.views import aga8_vs_refprop as view

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "aga8_vs_refprop"
METADATA_FILE = DATA_DIR / "metadata.json"
RESULTS_DIR = DATA_DIR / "results"

_ID_PATTERN = re.compile(r"^(gasmet_\d{2}|klab_gas_0[1-3])$")
_GASMET_ID_PATTERN = re.compile(r"^gasmet_\d{2}$")
_KLAB_ID_PATTERN = re.compile(r"^klab_gas_0[1-3]$")
_ALLOWED_COMPONENTS = set(view.COMPONENT_ORDER)
_REQUIRED_DEV_COLUMNS = [
    "P_bara",
    "GERG_rho_rel_dev", "DETAIL_rho_rel_dev",
    "GERG_w_rel_dev", "DETAIL_w_rel_dev",
    "GERG_Z_rel_dev", "DETAIL_Z_rel_dev",
    "GERG_kappa_rel_dev", "DETAIL_kappa_rel_dev",
]


def _raw_metadata():
    with open(METADATA_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_metadata_contains_50_gasmet_and_3_klab_gases():
    metadata_df = view.load_metadata()
    assert len(metadata_df) == 53
    assert int(metadata_df["id"].str.match(_GASMET_ID_PATTERN).sum()) == 50
    assert int(metadata_df["id"].str.match(_KLAB_ID_PATTERN).sum()) == 3


def test_all_gas_ids_match_anonymized_patterns():
    metadata_df = view.load_metadata()
    for gas_id in metadata_df["id"]:
        assert _ID_PATTERN.match(gas_id), f"id {gas_id} is not anonymized"


def test_result_files_are_only_anonymized_ids():
    expected = {f"gasmet_{index:02d}.csv" for index in range(1, 51)}
    expected.update({f"klab_gas_{index:02d}.csv" for index in range(1, 4)})
    actual = {path.name for path in RESULTS_DIR.glob("*.csv")}
    assert actual == expected


def test_no_field_name_leakage_in_metadata():
    # Regression guard: every top-level key is an anonymized id, and compositions only
    # ever use known AGA8 component names — no free-text station identifiers anywhere.
    metadata = _raw_metadata()
    for gas_id, entry in metadata.items():
        assert _ID_PATTERN.match(gas_id)
        assert entry["id"] == gas_id
        assert set(entry["composition"]).issubset(_ALLOWED_COMPONENTS)


def test_quality_groups_are_valid_and_sum_to_total_gases():
    metadata_df = view.load_metadata()
    allowed = set(view.QUALITY_GROUPS)
    assert set(metadata_df["quality_group"]).issubset(allowed)
    counts = metadata_df["quality_group"].value_counts().to_dict()
    assert sum(counts.values()) == 53


def test_gasmet_quality_distribution_matches_aga8_standard():
    # Locks in the standard-compliant classification (AGA8 Part 2, Table 5), computed via
    # the gasprops built-in validate_composition. Regression guard against the C6+/grouped
    # GERG-limit bug that previously mis-classified 11 stations as Intermediate.
    metadata_df = view.load_metadata()
    gasmet_df = metadata_df[metadata_df["id"].str.match(_GASMET_ID_PATTERN)]
    counts = gasmet_df["quality_group"].value_counts().to_dict()
    assert counts["Pipeline Quality"] == 23
    assert counts["Intermediate Quality"] == 8
    assert counts["Outside Intermediate Quality"] == 19


def test_klab_gases_are_outside_intermediate_quality():
    metadata_df = view.load_metadata()
    klab_df = metadata_df[metadata_df["id"].str.match(_KLAB_ID_PATTERN)]
    assert len(klab_df) == 3
    assert set(klab_df["data_source"]) == {"K-lab"}
    assert set(klab_df["quality_group"]) == {"Outside Intermediate Quality"}


def test_klab_gas_detection_uses_anonymized_id_prefix():
    assert view._is_klab_gas("klab_gas_01")
    assert not view._is_klab_gas("gasmet_01")


def test_klab_selection_covers_low_medium_and_just_below_one_percent_detail_density_deviation():
    metadata = _raw_metadata()
    assert metadata["klab_gas_01"]["detail_density_abs_max_rel_dev"] == pytest.approx(0.300451513)
    assert metadata["klab_gas_02"]["detail_density_abs_max_rel_dev"] == pytest.approx(0.633291165)
    assert metadata["klab_gas_03"]["detail_density_abs_max_rel_dev"] == pytest.approx(0.938754215)
    assert metadata["klab_gas_02"]["composition"]["C3"] == pytest.approx(9.912156)


def test_grouped_gerg_limits_are_enforced():
    # A composition within each individual iC5/nC5 limit but exceeding the grouped
    # iC5+nC5 (<=0.5%) and C8+ (<=0.05%) intermediate limits must be flagged. This is the
    # exact grouping an earlier external validation script missed for GERG.
    composition = {
        "C1": 90.0, "C2": 5.0, "C3": 3.0,
        "iC5": 0.4, "nC5": 0.4,
        "nC8": 0.03, "nC9": 0.02, "nC10": 0.02,
    }
    from gasprop.validation import validate_composition

    names = {issue.name for issue in validate_composition(composition, "GERG-2008")}
    assert "iC5+nC5" in names
    assert "nC8+nC9+nC10" in names


def test_component_violations_excludes_total_check():
    # component_violations must count only range violations, never the sum-to-100 issue.
    off_total = {"C1": 50.0}  # sums to 50%, but C1 range itself is satisfied for GERG
    assert view.component_violations(off_total, "GERG-2008") == 0


def test_outside_pipeline_composite_filter_covers_non_pipeline():
    # "Outside pipeline quality range" = Intermediate + Outside Intermediate (i.e. everything
    # that is not Pipeline Quality). It must equal the total minus the Pipeline count.
    groups = view.COMPOSITE_FILTERS["Outside Pipeline Quality Range"]
    assert set(groups) == {"Intermediate Quality", "Outside Intermediate Quality"}
    metadata_df = view.load_metadata()
    metadata_df = metadata_df[metadata_df["id"].str.match(_GASMET_ID_PATTERN)]
    non_pipeline = int((metadata_df["quality_group"] != "Pipeline Quality").sum())
    covered = int(metadata_df["quality_group"].isin(groups).sum())
    assert covered == non_pipeline == 27


def test_quality_group_matches_violation_counts():
    # Pipeline = no DETAIL violations; Intermediate = DETAIL>0 but GERG==0;
    # Outside = GERG>0. This mirrors the classification stored during data prep.
    for entry in _raw_metadata().values():
        detail = entry["detail_violations"]
        gerg = entry["gerg_violations"]
        if detail == 0:
            expected = "Pipeline Quality"
        elif gerg == 0:
            expected = "Intermediate Quality"
        else:
            expected = "Outside Intermediate Quality"
        assert entry["quality_group"] == expected


def test_results_have_required_deviation_columns():
    results_df = view.load_results("gasmet_01")
    for column in _REQUIRED_DEV_COLUMNS:
        assert column in results_df.columns
    assert results_df["P_bara"].is_monotonic_increasing
    assert results_df["P_bara"].min() == pytest.approx(10.0)


def test_all_results_loader_returns_every_anonymized_result_file():
    all_results = view.load_all_results()
    assert len(all_results) == 53
    assert "gasmet_01" in all_results
    assert "klab_gas_03" in all_results


def test_c6_plus_equals_sum_of_heavy_components():
    composition = view._load_compositions()["gasmet_01"]
    expected = sum(composition[component] for component in view.C6_PLUS_COMPONENTS)
    assert view._c6_plus_mol_pct("gasmet_01") == pytest.approx(expected)


def test_composition_dataframe_has_expected_shape():
    df = view._composition_dataframe("gasmet_01")
    assert list(df.columns) == ["Component", "Mol %"]
    assert set(df["Component"]).issubset(_ALLOWED_COMPONENTS)


def test_wide_composition_dataframe_has_one_column_per_gas_and_c6_plus_row():
    df = view._composition_wide_dataframe(["gasmet_01", "klab_gas_01"])
    assert list(df.columns) == ["Component", "gasmet_01", "klab_gas_01"]
    assert "C6+ (nC6…nC10)" in df["Component"].tolist()
    gasmet_c6_plus = df.loc[df["Component"] == "C6+ (nC6…nC10)", "gasmet_01"].iloc[0]
    assert gasmet_c6_plus == pytest.approx(view._c6_plus_mol_pct("gasmet_01"))


def test_scatter_dataframe_can_plot_density_deviation_against_c3_content():
    metadata_df = view.load_metadata()
    gas_ids = ["gasmet_01", "gasmet_02"]
    results = {gas_id: view.load_results(gas_id) for gas_id in gas_ids}
    df = view._scatter_dataframe(
        gas_ids,
        metadata_df,
        results,
        "C3",
        "DETAIL",
        "Mass Density",
        "At selected pressure",
        100.0,
    )
    composition = view._load_compositions()["gasmet_01"]
    expected_deviation = results["gasmet_01"].loc[
        results["gasmet_01"]["P_bara"] == 100.0, "DETAIL_rho_rel_dev"
    ].iloc[0]
    assert list(df.columns) == ["Gas", "Quality range", "Data source", "X", "Relative deviation [%]"]
    assert df.loc[df["Gas"] == "gasmet_01", "X"].iloc[0] == pytest.approx(composition["C3"])
    assert df.loc[df["Gas"] == "gasmet_01", "Relative deviation [%]"].iloc[0] == pytest.approx(
        expected_deviation
    )


def test_scatter_dataframe_supports_c6_plus_and_max_absolute_deviation():
    metadata_df = view.load_metadata()
    results = {"gasmet_01": view.load_results("gasmet_01")}
    df = view._scatter_dataframe(
        ["gasmet_01"],
        metadata_df,
        results,
        "C6+ (nC6…nC10)",
        "GERG-2008",
        "Mass Density",
        "Maximum absolute",
        None,
    )
    assert df["X"].iloc[0] == pytest.approx(view._c6_plus_mol_pct("gasmet_01"))
    assert df["Relative deviation [%]"].iloc[0] == pytest.approx(
        results["gasmet_01"]["GERG_rho_rel_dev"].abs().max()
    )


def test_scatter_figure_groups_markers_by_selected_category():
    metadata_df = view.load_metadata()
    gas_ids = ["gasmet_01", "klab_gas_01"]
    results = {gas_id: view.load_results(gas_id) for gas_id in gas_ids}
    df = view._scatter_dataframe(
        gas_ids,
        metadata_df,
        results,
        "C3",
        "DETAIL",
        "Mass Density",
        "At selected pressure",
        100.0,
    )
    figure = view._create_scatter_figure(
        df,
        "C3 [mol %]",
        "DETAIL Mass Density relative deviation [%] at 100 bara",
        "Data source",
    )
    assert {trace.name for trace in figure.data} == {"Norwegian gas grid", "K-lab"}


def test_grouped_figure_uses_combined_traces_for_performance():
    results = {
        "gasmet_01": view.load_results("gasmet_01"),
        "gasmet_02": view.load_results("gasmet_02"),
        "klab_gas_01": view.load_results("klab_gas_01"),
    }
    figure = view._create_group_figure(
        results,
        ["GERG-2008", "DETAIL"],
        "test",
        [-1.0, 1.0],
        {"GERG-2008": "#0000a2", "DETAIL": "#E69F00"},
    )
    assert len(figure.data) == 8


def test_tab_is_registered_in_view_map():
    assert VIEW_MAP.get("AGA8 vs REFPROP") is view.render
