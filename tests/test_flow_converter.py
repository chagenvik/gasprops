from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import gasprop.flow_converter as fc
from gasprop.app import VIEW_MAP, METERING_TAB_LABELS, _apply_tab_highlight_selectors
from gasprop.dp_flow import DPFlowError
from gasprop.views import flow_converter as flow_converter_view


NATURAL_GAS = {
    "N2": 1.0,
    "CO2": 1.5,
    "C1": 90.0,
    "C2": 4.5,
    "C3": 2.0,
    "iC4": 0.4,
    "nC4": 0.4,
    "iC5": 0.1,
    "nC5": 0.1,
}


def _convert(**kwargs):
    params = {
        "composition": NATURAL_GAS,
        "value": 100_000.0,
        "basis": "mass",
        "pressure": 60.0,
        "temperature": 20.0,
    }
    params.update(kwargs)
    composition = params.pop("composition")
    value = params.pop("value")
    basis = params.pop("basis")
    pressure = params.pop("pressure")
    temperature = params.pop("temperature")
    return fc.convert_flow(composition, value, basis, pressure, temperature, **params)


# ── Densities ─────────────────────────────────────────────────────────────────
def test_densities_match_direct_aga8_calls():
    import pvtlib

    from gasprop.dp_flow import _normalised_mol_percent

    aga8 = pvtlib.AGA8("GERG-2008")
    normalised = _normalised_mol_percent(NATURAL_GAS)
    actual = aga8.calculate_from_PT(
        composition=normalised, pressure=60.0, temperature=20.0,
        pressure_unit="bara", temperature_unit="C",
    )
    standard = aga8.calculate_from_PT(
        composition=normalised, pressure=1.01325, temperature=15.0,
        pressure_unit="bara", temperature_unit="C",
    )

    result = _convert()

    assert result.actual_density_kg_m3 == pytest.approx(actual["rho"])
    assert result.standard_density_kg_sm3 == pytest.approx(standard["rho"])


def test_default_standard_conditions_are_1_01325_bara_and_15_degc():
    std = fc.StandardConditions()
    assert std.pressure_bara == pytest.approx(1.01325)
    assert std.temperature_c == pytest.approx(15.0)


# ── Core conversion ───────────────────────────────────────────────────────────
def test_mass_flow_converts_to_actual_volume_via_actual_density():
    result = _convert(value=100_000.0, basis="mass", time_unit="h")
    mass, actual, _ = result.in_time_unit("h")

    assert mass == pytest.approx(100_000.0)
    assert actual == pytest.approx(100_000.0 / result.actual_density_kg_m3)


def test_mass_flow_converts_to_standard_volume_via_standard_density():
    result = _convert(value=100_000.0, basis="mass", time_unit="h")
    _, _, standard = result.in_time_unit("h")

    assert standard == pytest.approx(100_000.0 / result.standard_density_kg_sm3)


def test_actual_volume_input_reproduces_the_same_mass_flow():
    from_mass = _convert(value=100_000.0, basis="mass", time_unit="h")
    _, actual_volume, _ = from_mass.in_time_unit("h")

    from_volume = _convert(value=actual_volume, basis="actual_volume", time_unit="h")

    assert from_volume.mass_flow_kg_s == pytest.approx(from_mass.mass_flow_kg_s)


def test_standard_volume_input_reproduces_the_same_mass_flow():
    from_mass = _convert(value=100_000.0, basis="mass", time_unit="h")
    _, _, standard_volume = from_mass.in_time_unit("h")

    from_standard = _convert(value=standard_volume, basis="standard_volume", time_unit="h")

    assert from_standard.mass_flow_kg_s == pytest.approx(from_mass.mass_flow_kg_s)


def test_volume_ratio_is_actual_density_over_standard_density():
    result = _convert()
    assert result.formation_volume_ratio == pytest.approx(
        result.actual_density_kg_m3 / result.standard_density_kg_sm3
    )


# ── Time basis ────────────────────────────────────────────────────────────────
def test_time_units_scale_by_exactly_3600_and_86400():
    result = _convert(value=100_000.0, basis="mass", time_unit="h")

    per_second = result.in_time_unit("s")
    per_hour = result.in_time_unit("h")
    per_day = result.in_time_unit("d")

    for second, hour, day in zip(per_second, per_hour, per_day):
        assert hour == pytest.approx(second * 3600.0)
        assert day == pytest.approx(second * 86400.0)


def test_input_time_unit_is_interpreted_correctly():
    per_hour = _convert(value=3600.0, basis="mass", time_unit="h")
    per_second = _convert(value=1.0, basis="mass", time_unit="s")

    assert per_hour.mass_flow_kg_s == pytest.approx(1.0)
    assert per_second.mass_flow_kg_s == pytest.approx(per_hour.mass_flow_kg_s)


def test_day_input_matches_equivalent_hourly_input():
    per_day = _convert(value=24_000.0, basis="mass", time_unit="d")
    per_hour = _convert(value=1_000.0, basis="mass", time_unit="h")

    assert per_day.mass_flow_kg_s == pytest.approx(per_hour.mass_flow_kg_s)


def test_unknown_time_unit_is_rejected():
    with pytest.raises(DPFlowError, match="Unsupported time unit"):
        _convert(time_unit="week")


# ── Mass unit ─────────────────────────────────────────────────────────────────
def test_tonnes_input_is_one_thousand_times_kilogram_input():
    in_tonnes = _convert(value=1.0, basis="mass", mass_unit="t", time_unit="h")
    in_kilograms = _convert(value=1000.0, basis="mass", mass_unit="kg", time_unit="h")

    assert in_tonnes.mass_flow_kg_s == pytest.approx(in_kilograms.mass_flow_kg_s)


def test_mass_unit_does_not_affect_volume_basis_input():
    # The mass unit only describes the input when converting *from* mass flow.
    with_kg = _convert(value=5000.0, basis="actual_volume", mass_unit="kg")
    with_tonnes = _convert(value=5000.0, basis="actual_volume", mass_unit="t")

    assert with_kg.mass_flow_kg_s == pytest.approx(with_tonnes.mass_flow_kg_s)


def test_unknown_mass_unit_is_rejected():
    with pytest.raises(DPFlowError, match="Unsupported mass unit"):
        _convert(mass_unit="lb")


# ── Standard conditions ───────────────────────────────────────────────────────
def test_normal_conditions_give_a_higher_standard_density_than_15_degc():
    sm3 = _convert(standard_conditions=fc.StandardConditions(1.01325, 15.0))
    nm3 = _convert(standard_conditions=fc.StandardConditions(1.01325, 0.0))

    assert nm3.standard_density_kg_sm3 > sm3.standard_density_kg_sm3


def test_colder_standard_conditions_give_fewer_standard_volumes_for_the_same_mass():
    sm3 = _convert(value=100_000.0, basis="mass", standard_conditions=fc.StandardConditions(1.01325, 15.0))
    nm3 = _convert(value=100_000.0, basis="mass", standard_conditions=fc.StandardConditions(1.01325, 0.0))

    assert nm3.standard_volume_flow_sm3_s < sm3.standard_volume_flow_sm3_s


def test_standard_conditions_do_not_affect_the_actual_volume_flow():
    sm3 = _convert(standard_conditions=fc.StandardConditions(1.01325, 15.0))
    nm3 = _convert(standard_conditions=fc.StandardConditions(2.0, 0.0))

    assert nm3.actual_volume_flow_m3_s == pytest.approx(sm3.actual_volume_flow_m3_s)


def test_every_standard_condition_preset_is_constructible():
    for label, (pressure, temperature) in fc.STANDARD_CONDITION_PRESETS.items():
        std = fc.StandardConditions(pressure, temperature)
        assert std.pressure_bara == pytest.approx(pressure), label
        assert std.temperature_c == pytest.approx(temperature), label


def test_us_standard_preset_is_60_degf():
    _, temperature = fc.STANDARD_CONDITION_PRESETS["US standard (1.01325 bara, 60 °F)"]
    assert temperature == pytest.approx((60.0 - 32.0) * 5.0 / 9.0)


def test_standard_conditions_reject_non_positive_pressure():
    with pytest.raises(DPFlowError, match="Standard pressure"):
        fc.StandardConditions(0.0, 15.0)


def test_standard_conditions_reject_temperature_at_absolute_zero():
    with pytest.raises(DPFlowError, match="Standard temperature"):
        fc.StandardConditions(1.01325, -273.15)


# ── Units on the actual conditions ────────────────────────────────────────────
def test_barg_and_kelvin_inputs_match_bara_and_celsius():
    bara = _convert(pressure=60.0, temperature=20.0)
    barg = _convert(
        pressure=60.0 - 1.01325, temperature=293.15,
        pressure_unit="barg", temperature_unit="K",
    )

    assert barg.pressure_bara == pytest.approx(bara.pressure_bara)
    assert barg.temperature_c == pytest.approx(bara.temperature_c)
    assert barg.actual_density_kg_m3 == pytest.approx(bara.actual_density_kg_m3)


# ── Validation ────────────────────────────────────────────────────────────────
def test_zero_flow_converts_to_zero_everywhere():
    result = _convert(value=0.0)
    assert result.mass_flow_kg_s == pytest.approx(0.0)
    assert result.actual_volume_flow_m3_s == pytest.approx(0.0)
    assert result.standard_volume_flow_sm3_s == pytest.approx(0.0)


def test_negative_flow_is_rejected():
    with pytest.raises(DPFlowError, match="Flow rate"):
        _convert(value=-1.0)


def test_unknown_basis_is_rejected():
    with pytest.raises(DPFlowError, match="Unknown flow basis"):
        _convert(basis="molar")


def test_non_positive_pressure_is_rejected():
    with pytest.raises(DPFlowError, match="Pressure"):
        _convert(pressure=0.0)


def test_empty_composition_is_rejected():
    with pytest.raises(DPFlowError, match="Composition total"):
        _convert(composition={"C1": 0.0})


def test_detail_equation_is_accepted_and_differs_slightly_from_gerg():
    gerg = _convert(equation="GERG-2008")
    detail = _convert(equation="DETAIL")

    assert gerg.actual_density_kg_m3 == pytest.approx(detail.actual_density_kg_m3, rel=1e-3)
    assert gerg.actual_density_kg_m3 != pytest.approx(detail.actual_density_kg_m3, rel=1e-12)


# ── View wiring ───────────────────────────────────────────────────────────────
def test_tab_is_registered_in_view_map():
    assert VIEW_MAP.get("Flow Converter") is flow_converter_view.render


def test_metering_tabs_are_the_last_two_tabs():
    order = list(VIEW_MAP.keys())
    assert order[-2:] == ["DP Flow Meter", "Flow Converter"]


def test_metering_tab_group_matches_the_registered_labels():
    assert METERING_TAB_LABELS == ("DP Flow Meter", "Flow Converter")
    for label in METERING_TAB_LABELS:
        assert label in VIEW_MAP


def test_dp_flow_meter_sits_directly_after_phase_envelope():
    order = list(VIEW_MAP.keys())
    assert order.index("DP Flow Meter") == order.index("Phase Envelope") + 1


def test_stylesheet_placeholders_are_all_expanded():
    css = _apply_tab_highlight_selectors(
        "__NEQSIM_TABS__ __NEQSIM_TABS_SELECTED__ "
        "__DATA_STUDY_TABS__ __DATA_STUDY_TABS_SELECTED__ "
        "__METERING_TABS__ __METERING_TABS_SELECTED__"
    )
    assert "__" not in css
    assert "nth-child(12)" in css
    assert "nth-child(13)" in css


def test_unresolved_stylesheet_placeholder_raises():
    with pytest.raises(ValueError, match="Unresolved tab highlight placeholders"):
        _apply_tab_highlight_selectors("__NOT_A_GROUP__")


def test_every_flow_basis_has_a_label():
    for basis in fc.FLOW_BASES:
        assert basis in fc.FLOW_BASIS_LABELS


def test_every_time_unit_has_a_label():
    for unit in fc.TIME_UNIT_SECONDS:
        assert unit in fc.TIME_UNIT_LABELS
