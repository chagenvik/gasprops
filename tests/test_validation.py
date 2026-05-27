from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gasprop.validation import validate_composition, validate_state


def _base_comp() -> dict[str, float]:
    return {"C1": 100.0}


def _with_group(group_values: dict[str, float]) -> dict[str, float]:
    comp = _base_comp()
    added = sum(group_values.values())
    comp["C1"] = 100.0 - added
    comp.update(group_values)
    return comp


def test_validation_detects_out_of_range():
    comp = {"C1": 40.0, "CO2": 40.0, "N2": 20.0}
    issues = validate_composition(comp, mode="DETAIL")
    assert len(issues) == 2
    assert {issue.name for issue in issues} == {"C1", "CO2"}


def test_state_validation():
    issues = validate_state(800.0, 500.0, mode="GERG-2008")
    assert len(issues) == 2
    assert {issue.name for issue in issues} == {"PRESSURE", "TEMPERATURE"}


def test_state_validation_within_range_detail():
    issues = validate_state(300.0, 100.0, mode="DETAIL")
    assert issues == []


def test_state_validation_within_range_gerg2008():
    issues = validate_state(600.0, 300.0, mode="GERG-2008")
    assert issues == []


def test_composition_within_range_detail_and_gerg2008():
    comp = {
        "N2": 1.02,
        "CO2": 2.04,
        "C1": 90.23,
        "C2": 6.11,
        "C3": 0.51,
        "iC4": 0.05,
        "nC4": 0.05,
    }

    issues_detail = validate_composition(comp, mode="DETAIL")
    issues_gerg = validate_composition(comp, mode="GERG-2008")

    assert issues_detail == []
    assert issues_gerg == []


def test_composition_expected_out_of_range_components_detail_and_gerg2008():
    comp = {
        "N2": 1.0456,
        "CO2": 2.0912,
        "C1": 85.0444,
        "C2": 5.1104,
        "C3": 4.1823,
        "iC4": 0.6273,
        "nC4": 1.0456,
        "iC5": 0.3137,
        "nC5": 0.3137,
        "nC6": 0.1046,
        "nC7": 0.0732,
        "nC8": 0.0418,
        "nC9": 0.0042,
        "nC10": 0.0021,
    }

    issues_detail = validate_composition(comp, mode="DETAIL")
    issues_gerg = validate_composition(comp, mode="GERG-2008")

    detail_names = {issue.name for issue in issues_detail}
    gerg_names = {issue.name for issue in issues_gerg}

    # DETAIL expected out-of-range components per request.
    assert {"C3", "iC4+nC4", "iC5+nC5", "nC6", "nC7"}.issubset(detail_names)

    # GERG expected out-of-range components per request: pentanes.
    assert {"iC5+nC5"}.issubset(gerg_names)


def test_group_ic4_nc4_passes_at_1p4_detail():
    comp = _with_group({"iC4": 0.7, "nC4": 0.7})
    names = {issue.name for issue in validate_composition(comp, mode="DETAIL")}
    assert "iC4+nC4" not in names


def test_group_ic4_nc4_passes_at_1p4_gerg2008():
    comp = _with_group({"iC4": 0.7, "nC4": 0.7})
    names = {issue.name for issue in validate_composition(comp, mode="GERG-2008")}
    assert "iC4+nC4" not in names


def test_group_ic4_nc4_fails_at_1p6_detail():
    comp = _with_group({"iC4": 0.8, "nC4": 0.8})
    names = {issue.name for issue in validate_composition(comp, mode="DETAIL")}
    assert "iC4+nC4" in names


def test_group_ic4_nc4_passes_at_1p6_gerg2008():
    comp = _with_group({"iC4": 0.8, "nC4": 0.8})
    names = {issue.name for issue in validate_composition(comp, mode="GERG-2008")}
    assert "iC4+nC4" not in names


def test_group_ic4_nc4_fails_at_6p2_gerg2008():
    comp = _with_group({"iC4": 3.1, "nC4": 3.1})
    names = {issue.name for issue in validate_composition(comp, mode="GERG-2008")}
    assert "iC4+nC4" in names


def test_group_ic4_nc4_fails_detail_with_0p9_and_0p65():
    comp = _with_group({"iC4": 0.9, "nC4": 0.65})
    names = {issue.name for issue in validate_composition(comp, mode="DETAIL")}
    assert "iC4+nC4" in names


def test_group_ic5_nc5_below_limit_passes_detail():
    comp = _with_group({"iC5": 0.2, "nC5": 0.2})
    names = {issue.name for issue in validate_composition(comp, mode="DETAIL")}
    assert "iC5+nC5" not in names


def test_group_ic5_nc5_below_limit_passes_gerg2008():
    comp = _with_group({"iC5": 0.2, "nC5": 0.2})
    names = {issue.name for issue in validate_composition(comp, mode="GERG-2008")}
    assert "iC5+nC5" not in names


def test_group_ic5_nc5_above_limit_fails_detail():
    comp = _with_group({"iC5": 0.3, "nC5": 0.3})
    names = {issue.name for issue in validate_composition(comp, mode="DETAIL")}
    assert "iC5+nC5" in names


def test_group_ic5_nc5_above_limit_fails_gerg2008():
    comp = _with_group({"iC5": 0.3, "nC5": 0.3})
    names = {issue.name for issue in validate_composition(comp, mode="GERG-2008")}
    assert "iC5+nC5" in names


def test_group_nc8_nc9_nc10_below_limit_passes_detail():
    comp = _with_group({"nC8": 0.01, "nC9": 0.01, "nC10": 0.01})
    names = {issue.name for issue in validate_composition(comp, mode="DETAIL")}
    assert "nC8+nC9+nC10" not in names


def test_group_nc8_nc9_nc10_below_limit_passes_gerg2008():
    comp = _with_group({"nC8": 0.01, "nC9": 0.01, "nC10": 0.01})
    names = {issue.name for issue in validate_composition(comp, mode="GERG-2008")}
    assert "nC8+nC9+nC10" not in names


def test_group_nc8_nc9_nc10_above_limit_fails_detail():
    comp = _with_group({"nC8": 0.02, "nC9": 0.02, "nC10": 0.02})
    names = {issue.name for issue in validate_composition(comp, mode="DETAIL")}
    assert "nC8+nC9+nC10" in names


def test_group_nc8_nc9_nc10_above_limit_fails_gerg2008():
    comp = _with_group({"nC8": 0.02, "nC9": 0.02, "nC10": 0.02})
    names = {issue.name for issue in validate_composition(comp, mode="GERG-2008")}
    assert "nC8+nC9+nC10" in names
