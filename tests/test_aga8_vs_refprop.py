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

_ID_PATTERN = re.compile(r"^gasmet_\d{2}$")
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


def test_metadata_contains_exactly_50_stations():
    metadata_df = view.load_metadata()
    assert len(metadata_df) == 50


def test_all_station_ids_match_gasmet_pattern():
    metadata_df = view.load_metadata()
    for station_id in metadata_df["id"]:
        assert _ID_PATTERN.match(station_id), f"id {station_id} is not anonymized"


def test_result_files_are_only_anonymized_ids():
    expected = {f"gasmet_{index:02d}.csv" for index in range(1, 51)}
    actual = {path.name for path in RESULTS_DIR.glob("*.csv")}
    assert actual == expected


def test_no_field_name_leakage_in_metadata():
    # Regression guard: every top-level key is an anonymized id, and compositions only
    # ever use known AGA8 component names — no free-text station identifiers anywhere.
    metadata = _raw_metadata()
    for station_id, entry in metadata.items():
        assert _ID_PATTERN.match(station_id)
        assert entry["id"] == station_id
        assert set(entry["composition"]).issubset(_ALLOWED_COMPONENTS)


def test_quality_groups_are_valid_and_sum_to_50():
    metadata_df = view.load_metadata()
    allowed = set(view.QUALITY_GROUPS)
    assert set(metadata_df["quality_group"]).issubset(allowed)
    counts = metadata_df["quality_group"].value_counts().to_dict()
    assert sum(counts.values()) == 50


def test_quality_distribution_matches_aga8_standard():
    # Locks in the standard-compliant classification (AGA8 Part 2, Table 5), computed via
    # the gasprops built-in validate_composition. Regression guard against the C6+/grouped
    # GERG-limit bug that previously mis-classified 11 stations as Intermediate.
    counts = view.load_metadata()["quality_group"].value_counts().to_dict()
    assert counts["Pipeline Quality"] == 23
    assert counts["Intermediate Quality"] == 8
    assert counts["Outside Intermediate Quality"] == 19


def test_grouped_gerg_limits_are_enforced():
    # A composition within each individual iC5/nC5 limit but exceeding the grouped
    # iC5+nC5 (<=0.5%) and C8+ (<=0.05%) intermediate limits must be flagged. This is the
    # exact grouping the earlier GFMW2026 code missed for GERG.
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


def test_c6_plus_equals_sum_of_heavy_components():
    composition = view._load_compositions()["gasmet_01"]
    expected = sum(composition[component] for component in view.C6_PLUS_COMPONENTS)
    assert view._c6_plus_mol_pct("gasmet_01") == pytest.approx(expected)


def test_composition_dataframe_has_expected_shape():
    df = view._composition_dataframe("gasmet_01")
    assert list(df.columns) == ["Component", "Mol %"]
    assert set(df["Component"]).issubset(_ALLOWED_COMPONENTS)


def test_tab_is_registered_in_view_map():
    assert VIEW_MAP.get("AGA8 vs REFPROP") is view.render
