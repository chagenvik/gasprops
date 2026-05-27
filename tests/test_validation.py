from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gasprop.validation import validate_composition, validate_state


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
    assert {"C3", "iC4", "nC4", "iC5", "nC5", "nC6", "nC7"}.issubset(detail_names)

    # GERG expected out-of-range components per request: pentanes.
    assert {"iC5", "nC5"}.issubset(gerg_names)
