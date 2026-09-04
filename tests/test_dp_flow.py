from pathlib import Path
import math
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pvtlib.metering import differential_pressure_flowmeters as dpm

import gasprop.dp_flow as dp_flow
from gasprop.app import VIEW_MAP, tab_nth_child_selector
from gasprop.views import dp_flow as dp_flow_view


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

VENTURI = dp_flow.MeterGeometry(meter_type="Venturi", pipe_diameter_mm=200.0, bore_diameter_mm=120.0)
ORIFICE = dp_flow.MeterGeometry(meter_type="Orifice", pipe_diameter_mm=200.0, bore_diameter_mm=120.0)
V_CONE = dp_flow.MeterGeometry(meter_type="V-cone", pipe_diameter_mm=200.0, bore_diameter_mm=140.0)


def _gas_state(viscosity_pa_s: float | None = 1.2e-5, **kwargs) -> dp_flow.GasState:
    """Gas state with a fixed viscosity so tests never depend on NeqSim."""
    params = {"pressure": 60.0, "temperature": 20.0}
    params.update(kwargs)
    return dp_flow.calculate_gas_state(
        NATURAL_GAS,
        viscosity_pa_s=viscosity_pa_s,
        **params,
    )


# ── Geometry ──────────────────────────────────────────────────────────────────
def test_venturi_beta_is_bore_over_pipe_diameter():
    assert VENTURI.beta == pytest.approx(0.6)


def test_v_cone_beta_follows_iso_5167_5_definition():
    expected = math.sqrt(1.0 - (140.0**2) / (200.0**2))
    assert V_CONE.beta == pytest.approx(expected)
    assert V_CONE.beta == pytest.approx(0.7141428, abs=1e-6)


def test_geometry_converts_millimetres_to_metres():
    assert VENTURI.D_m == pytest.approx(0.200)
    assert VENTURI.bore_m == pytest.approx(0.120)


def test_geometry_rejects_bore_larger_than_pipe():
    with pytest.raises(dp_flow.DPFlowError, match="smaller than the pipe diameter"):
        dp_flow.MeterGeometry(meter_type="Venturi", pipe_diameter_mm=100.0, bore_diameter_mm=100.0)


def test_geometry_rejects_unknown_meter_type():
    with pytest.raises(dp_flow.DPFlowError, match="Unknown meter type"):
        dp_flow.MeterGeometry(meter_type="Wedge", pipe_diameter_mm=100.0, bore_diameter_mm=50.0)


def test_geometry_rejects_unknown_orifice_tapping():
    with pytest.raises(dp_flow.DPFlowError, match="Unknown orifice tapping"):
        dp_flow.MeterGeometry(
            meter_type="Orifice", pipe_diameter_mm=100.0, bore_diameter_mm=50.0, tapping="radius"
        )


def test_geometry_rejects_non_positive_diameter():
    with pytest.raises(dp_flow.DPFlowError, match="Pipe diameter"):
        dp_flow.MeterGeometry(meter_type="Venturi", pipe_diameter_mm=0.0, bore_diameter_mm=50.0)


# ── Unit conversion ───────────────────────────────────────────────────────────
def test_pressure_unit_conversion_to_bara():
    assert dp_flow._to_bara(10.0, "bara") == pytest.approx(10.0)
    assert dp_flow._to_bara(10.0, "barg") == pytest.approx(11.01325)
    assert dp_flow._to_bara(1000.0, "kPa") == pytest.approx(10.0)
    assert dp_flow._to_bara(1.0, "MPa") == pytest.approx(10.0)


def test_pressure_unit_conversion_rejects_unknown_unit():
    with pytest.raises(dp_flow.DPFlowError, match="Unsupported pressure unit"):
        dp_flow._to_bara(10.0, "psi")


def test_temperature_unit_conversion_to_celsius():
    assert dp_flow._to_celsius(15.0, "C") == pytest.approx(15.0)
    assert dp_flow._to_celsius(288.15, "K") == pytest.approx(15.0)


def test_temperature_unit_conversion_rejects_unknown_unit():
    with pytest.raises(dp_flow.DPFlowError, match="Unsupported temperature unit"):
        dp_flow._to_celsius(60.0, "F")


# ── Gas state ─────────────────────────────────────────────────────────────────
def test_gas_state_matches_direct_aga8_call():
    import pvtlib

    reference = pvtlib.AGA8("GERG-2008").calculate_from_PT(
        composition=dp_flow._normalised_mol_percent(NATURAL_GAS),
        pressure=60.0,
        temperature=20.0,
        pressure_unit="bara",
        temperature_unit="C",
    )
    state = _gas_state()

    assert state.density_kg_m3 == pytest.approx(reference["rho"])
    assert state.kappa == pytest.approx(reference["kappa"])
    assert state.z == pytest.approx(reference["z"])
    assert state.molar_mass_g_mol == pytest.approx(reference["mm"])
    assert state.speed_of_sound_m_s == pytest.approx(reference["w"])


def test_standard_density_is_evaluated_at_1_01325_bara_and_15_degc():
    import pvtlib

    reference = pvtlib.AGA8("GERG-2008").calculate_from_PT(
        composition=dp_flow._normalised_mol_percent(NATURAL_GAS),
        pressure=1.01325,
        temperature=15.0,
        pressure_unit="bara",
        temperature_unit="C",
    )
    assert dp_flow.standard_density(NATURAL_GAS) == pytest.approx(reference["rho"])


def test_standard_density_is_independent_of_composition_scaling():
    scaled = {key: value * 3.0 for key, value in NATURAL_GAS.items()}
    assert dp_flow.standard_density(scaled) == pytest.approx(dp_flow.standard_density(NATURAL_GAS))


def test_gas_state_accepts_barg_and_kelvin_inputs():
    bara_state = _gas_state(pressure=60.0, temperature=20.0)
    barg_state = _gas_state(
        pressure=60.0 - 1.01325, temperature=293.15, pressure_unit="barg", temperature_unit="K"
    )
    assert barg_state.pressure_bara == pytest.approx(bara_state.pressure_bara)
    assert barg_state.temperature_c == pytest.approx(bara_state.temperature_c)
    assert barg_state.density_kg_m3 == pytest.approx(bara_state.density_kg_m3)


def test_manual_viscosity_is_reported_as_manual_source():
    state = _gas_state(viscosity_pa_s=1.5e-5)
    assert state.viscosity_pa_s == pytest.approx(1.5e-5)
    assert state.viscosity_source == "Manual"


def test_gas_state_rejects_non_positive_viscosity():
    with pytest.raises(dp_flow.DPFlowError, match="viscosity"):
        _gas_state(viscosity_pa_s=0.0)


def test_gas_state_rejects_empty_composition():
    with pytest.raises(dp_flow.DPFlowError, match="Composition total"):
        dp_flow.calculate_gas_state({"C1": 0.0}, 60.0, 20.0, viscosity_pa_s=1.2e-5)


def test_viscosity_from_neqsim_returns_none_for_empty_composition():
    assert dp_flow.viscosity_from_neqsim({"C1": 0.0}, 60.0, 20.0) is None


def test_automatic_viscosity_is_reported_as_neqsim_source(monkeypatch):
    monkeypatch.setattr(dp_flow, "viscosity_from_neqsim", lambda *args, **kwargs: 1.31e-5)
    state = _gas_state(viscosity_pa_s=None)

    assert state.viscosity_pa_s == pytest.approx(1.31e-5)
    assert state.viscosity_source == "NeqSim (SRK)"


def test_detail_and_gerg_give_different_densities():
    gerg = _gas_state(equation="GERG-2008")
    detail = _gas_state(equation="DETAIL")
    assert gerg.density_kg_m3 != pytest.approx(detail.density_kg_m3, rel=1e-12)
    assert gerg.density_kg_m3 == pytest.approx(detail.density_kg_m3, rel=1e-3)


# ── Venturi ───────────────────────────────────────────────────────────────────
def test_venturi_flow_matches_pvtlib_reference():
    state = _gas_state()
    result = dp_flow.calculate_dp_flow(VENTURI, state, 500.0)

    epsilon = dpm.calculate_expansibility_venturi(
        P1=state.pressure_bara, dP=500.0, beta=VENTURI.beta, kappa=state.kappa
    )
    reference = dpm.calculate_flow_venturi(
        D=0.200, d=0.120, dP=500.0, rho1=state.density_kg_m3, C=0.984, epsilon=epsilon
    )

    assert result.mass_flow_kg_h == pytest.approx(reference["MassFlow"])
    assert result.volume_flow_m3_h == pytest.approx(reference["VolFlow"])
    assert result.velocity_m_s == pytest.approx(reference["Velocity"])
    assert result.discharge_coefficient == pytest.approx(0.984)
    assert result.expansibility == pytest.approx(epsilon)


def test_venturi_uses_iso_default_discharge_coefficient():
    result = dp_flow.calculate_dp_flow(VENTURI, _gas_state(), 500.0)
    assert result.discharge_coefficient == pytest.approx(dp_flow.DEFAULT_C_VENTURI)
    assert result.discharge_coefficient_source == "ISO 5167-4 default (as cast)"


def test_venturi_manual_discharge_coefficient_scales_mass_flow_linearly():
    state = _gas_state()
    default = dp_flow.calculate_dp_flow(VENTURI, state, 500.0)
    calibrated = dp_flow.calculate_dp_flow(VENTURI, state, 500.0, discharge_coefficient=0.995)

    assert calibrated.discharge_coefficient_source == "Manual"
    assert calibrated.mass_flow_kg_h == pytest.approx(default.mass_flow_kg_h * 0.995 / 0.984)


def test_mass_flow_scales_with_square_root_of_dp_at_fixed_coefficients():
    state = _gas_state()
    low = dp_flow.calculate_dp_flow(VENTURI, state, 100.0, expansibility=1.0)
    high = dp_flow.calculate_dp_flow(VENTURI, state, 400.0, expansibility=1.0)
    assert high.mass_flow_kg_h == pytest.approx(2.0 * low.mass_flow_kg_h)


def test_expansibility_is_below_one_for_compressible_gas():
    result = dp_flow.calculate_dp_flow(VENTURI, _gas_state(), 500.0)
    assert 0.9 < result.expansibility < 1.0
    assert result.expansibility_source == "Calculated from AGA8 kappa"


def test_zero_dp_gives_zero_flow_and_unity_expansibility():
    result = dp_flow.calculate_dp_flow(VENTURI, _gas_state(), 0.0)
    assert result.mass_flow_kg_h == pytest.approx(0.0)
    assert result.std_volume_flow_sm3_h == pytest.approx(0.0)
    assert result.expansibility == pytest.approx(1.0)
    assert result.pressure_ratio == pytest.approx(1.0)


# ── Orifice ───────────────────────────────────────────────────────────────────
def test_orifice_flow_matches_pvtlib_reference_with_iterated_coefficient():
    state = _gas_state()
    result = dp_flow.calculate_dp_flow(ORIFICE, state, 500.0)

    epsilon = dpm.calculate_expansibility_orifice(
        P1=state.pressure_bara, dP=500.0, beta=ORIFICE.beta, kappa=state.kappa
    )
    reference = dpm.calculate_flow_orifice(
        D=0.200, d=0.120, dP=500.0, rho1=state.density_kg_m3, mu=1.2e-5,
        epsilon=epsilon, tapping="corner",
    )

    assert result.mass_flow_kg_h == pytest.approx(reference["MassFlow"])
    assert result.discharge_coefficient == pytest.approx(reference["C"])
    assert result.reynolds_number == pytest.approx(reference["Re"])
    assert result.discharge_coefficient_source == "Reader-Harris/Gallagher (corner tappings)"


def test_orifice_discharge_coefficient_is_close_to_typical_value():
    result = dp_flow.calculate_dp_flow(ORIFICE, _gas_state(), 500.0)
    assert 0.59 < result.discharge_coefficient < 0.62


def test_orifice_tapping_type_changes_discharge_coefficient():
    state = _gas_state()
    corner = dp_flow.calculate_dp_flow(ORIFICE, state, 500.0)
    flange_geometry = dp_flow.MeterGeometry(
        meter_type="Orifice", pipe_diameter_mm=200.0, bore_diameter_mm=120.0, tapping="flange"
    )
    flange = dp_flow.calculate_dp_flow(flange_geometry, state, 500.0)
    assert corner.discharge_coefficient != pytest.approx(flange.discharge_coefficient, rel=1e-12)


def test_orifice_without_viscosity_and_without_c_raises(monkeypatch):
    monkeypatch.setattr(dp_flow, "viscosity_from_neqsim", lambda *args, **kwargs: None)
    state = _gas_state(viscosity_pa_s=None)

    assert state.viscosity_pa_s is None
    assert state.viscosity_source == "Unavailable"
    with pytest.raises(dp_flow.DPFlowError, match="Reader-Harris/Gallagher"):
        dp_flow.calculate_dp_flow(ORIFICE, state, 500.0)


def test_orifice_with_manual_c_does_not_need_iteration():
    state = _gas_state()
    result = dp_flow.calculate_dp_flow(ORIFICE, state, 500.0, discharge_coefficient=0.6)
    assert result.discharge_coefficient == pytest.approx(0.6)
    assert result.discharge_coefficient_source == "Manual"


# ── V-cone ────────────────────────────────────────────────────────────────────
def test_v_cone_flow_matches_pvtlib_reference():
    state = _gas_state()
    result = dp_flow.calculate_dp_flow(V_CONE, state, 500.0)

    epsilon = dpm.calculate_expansibility_Stewart_V_cone(
        beta=V_CONE.beta, P1=state.pressure_bara, dP=500.0, k=state.kappa
    )
    reference = dpm.calculate_flow_V_cone(
        D=0.200, beta=V_CONE.beta, dP=500.0, rho1=state.density_kg_m3, C=0.82, epsilon=epsilon
    )

    assert result.mass_flow_kg_h == pytest.approx(reference["MassFlow"])
    assert result.discharge_coefficient == pytest.approx(dp_flow.DEFAULT_C_V_CONE)


def test_v_cone_reynolds_number_is_derived_from_viscosity():
    state = _gas_state()
    result = dp_flow.calculate_dp_flow(V_CONE, state, 500.0)
    expected = state.density_kg_m3 * result.velocity_m_s * V_CONE.D_m / state.viscosity_pa_s
    assert result.reynolds_number == pytest.approx(expected)


def test_reynolds_number_is_none_when_viscosity_is_unavailable(monkeypatch):
    monkeypatch.setattr(dp_flow, "viscosity_from_neqsim", lambda *args, **kwargs: None)
    state = _gas_state(viscosity_pa_s=None)

    result = dp_flow.calculate_dp_flow(V_CONE, state, 500.0)
    assert result.reynolds_number is None


# ── Standard volume conversion ────────────────────────────────────────────────
def test_standard_volume_flow_is_mass_flow_over_standard_density():
    state = _gas_state()
    result = dp_flow.calculate_dp_flow(VENTURI, state, 500.0)
    assert result.std_volume_flow_sm3_h == pytest.approx(
        result.mass_flow_kg_h / state.standard_density_kg_sm3
    )
    assert result.std_volume_flow_sm3_d == pytest.approx(result.std_volume_flow_sm3_h * 24.0)


# ── Input validation ──────────────────────────────────────────────────────────
def test_negative_dp_is_rejected():
    with pytest.raises(dp_flow.DPFlowError, match="Differential pressure"):
        dp_flow.calculate_dp_flow(VENTURI, _gas_state(), -10.0)


def test_dp_larger_than_upstream_pressure_is_rejected():
    with pytest.raises(dp_flow.DPFlowError, match="larger than the upstream pressure"):
        dp_flow.calculate_dp_flow(VENTURI, _gas_state(pressure=1.5), 2000.0)


def test_non_positive_manual_expansibility_is_rejected():
    with pytest.raises(dp_flow.DPFlowError, match="Expansibility"):
        dp_flow.calculate_dp_flow(VENTURI, _gas_state(), 500.0, expansibility=0.0)


# ── ISO 5167 range checks ─────────────────────────────────────────────────────
def test_in_range_venturi_produces_no_warnings():
    # Low dP keeps the Reynolds number inside the ISO 5167-4 range of use (2e5-2e6).
    result = dp_flow.calculate_dp_flow(VENTURI, _gas_state(), 8.0)
    assert result.reynolds_number == pytest.approx(1.8e6, rel=0.1)
    assert result.warnings == ()


def test_small_pipe_and_low_beta_venturi_reports_both_issues():
    geometry = dp_flow.MeterGeometry(meter_type="Venturi", pipe_diameter_mm=50.0, bore_diameter_mm=10.0)
    result = dp_flow.calculate_dp_flow(geometry, _gas_state(), 500.0)

    assert len(result.warnings) == 2
    assert any("Pipe diameter D" in message for message in result.warnings)
    assert any("Beta" in message for message in result.warnings)


def test_orifice_bore_below_12_5_mm_is_flagged():
    geometry = dp_flow.MeterGeometry(meter_type="Orifice", pipe_diameter_mm=60.0, bore_diameter_mm=10.0)
    result = dp_flow.calculate_dp_flow(geometry, _gas_state(), 500.0)
    assert any("below the ISO 5167-2 minimum of 12.5 mm" in message for message in result.warnings)


def test_low_pressure_ratio_is_flagged():
    state = _gas_state(pressure=2.0)
    result = dp_flow.calculate_dp_flow(VENTURI, state, 600.0)
    assert any("Pressure ratio" in message for message in result.warnings)


def test_low_reynolds_number_is_flagged_for_venturi():
    state = _gas_state(viscosity_pa_s=1.0e-2)
    result = dp_flow.calculate_dp_flow(VENTURI, state, 10.0)
    assert any("below the ISO 5167 minimum" in message for message in result.warnings)


def test_high_reynolds_number_is_flagged_for_venturi():
    state = _gas_state(viscosity_pa_s=1.0e-7)
    result = dp_flow.calculate_dp_flow(VENTURI, state, 500.0)
    assert any("above the ISO 5167 maximum" in message for message in result.warnings)


# ── Inverse solve (sizing) ────────────────────────────────────────────────────
def test_solve_dp_for_mass_flow_round_trips_through_forward_calculation():
    state = _gas_state()
    forward = dp_flow.calculate_dp_flow(VENTURI, state, 437.5)

    solved = dp_flow.solve_dp_for_mass_flow(VENTURI, state, forward.mass_flow_kg_h)

    assert solved.differential_pressure_mbar == pytest.approx(437.5, rel=1e-6)
    assert solved.mass_flow_kg_h == pytest.approx(forward.mass_flow_kg_h, rel=1e-8)


def test_solve_dp_for_std_volume_flow_round_trips_through_forward_calculation():
    state = _gas_state()
    forward = dp_flow.calculate_dp_flow(ORIFICE, state, 620.0)

    solved = dp_flow.solve_dp_for_std_volume_flow(ORIFICE, state, forward.std_volume_flow_sm3_h)

    assert solved.differential_pressure_mbar == pytest.approx(620.0, rel=1e-6)
    assert solved.std_volume_flow_sm3_h == pytest.approx(forward.std_volume_flow_sm3_h, rel=1e-8)


def test_solve_dp_respects_the_dp_ceiling():
    state = _gas_state()
    reachable = dp_flow.calculate_dp_flow(VENTURI, state, 100.0)

    with pytest.raises(dp_flow.DPFlowError, match="cannot be reached"):
        dp_flow.solve_dp_for_mass_flow(
            VENTURI, state, reachable.mass_flow_kg_h * 10.0, dp_max_mbar=100.0
        )


def test_solve_dp_rejects_non_positive_target():
    with pytest.raises(dp_flow.DPFlowError, match="Target mass flow"):
        dp_flow.solve_dp_for_mass_flow(VENTURI, _gas_state(), 0.0)


def test_solve_dp_for_std_volume_rejects_non_positive_target():
    with pytest.raises(dp_flow.DPFlowError, match="Target standard volume flow"):
        dp_flow.solve_dp_for_std_volume_flow(VENTURI, _gas_state(), -5.0)


# ── Convenience wrapper ───────────────────────────────────────────────────────
def test_convenience_wrapper_matches_two_step_calculation():
    state = _gas_state()
    expected = dp_flow.calculate_dp_flow(VENTURI, state, 500.0)

    actual = dp_flow.calculate_dp_flow_from_composition(
        NATURAL_GAS, VENTURI, 500.0, 60.0, 20.0, viscosity_pa_s=1.2e-5
    )

    assert actual.mass_flow_kg_h == pytest.approx(expected.mass_flow_kg_h)
    assert actual.std_volume_flow_sm3_h == pytest.approx(expected.std_volume_flow_sm3_h)


# ── View wiring ───────────────────────────────────────────────────────────────
def test_tab_is_registered_in_view_map():
    assert VIEW_MAP.get("DP Flow Meter") is dp_flow_view.render


def test_every_meter_type_has_a_diagram_file():
    for meter_type in dp_flow.METER_TYPES:
        file_name = dp_flow_view.DIAGRAMS[meter_type]
        assert (dp_flow_view._DIAGRAM_DIR / file_name).exists()


def test_diagram_data_uri_is_inline_svg():
    data_uri = dp_flow_view._diagram_data_uri(dp_flow_view.DIAGRAMS["Venturi"])
    assert data_uri is not None
    assert data_uri.startswith("data:image/svg+xml;base64,")


def test_diagram_data_uri_returns_none_for_missing_file():
    assert dp_flow_view._diagram_data_uri("does_not_exist.svg") is None


def test_every_meter_type_has_a_bore_label_and_description():
    for meter_type in dp_flow.METER_TYPES:
        assert meter_type in dp_flow_view.BORE_LABELS
        assert meter_type in dp_flow_view.METER_DESCRIPTIONS


def test_tab_highlight_selectors_follow_view_map_order():
    order = list(VIEW_MAP.keys())
    flash_index = order.index("Flash Calculation") + 1
    phase_index = order.index("Phase Envelope") + 1

    selector = tab_nth_child_selector(("Flash Calculation", "Phase Envelope"))

    assert f"nth-child({flash_index})" in selector
    assert f"nth-child({phase_index})" in selector


def test_tab_highlight_selector_appends_the_given_suffix():
    selector = tab_nth_child_selector(("AGA8 vs REFPROP",), '[aria-selected="true"]')
    assert selector.endswith('[aria-selected="true"]')
    assert selector.count("nth-child") == 1


def test_tab_highlight_selector_ignores_unknown_labels():
    assert tab_nth_child_selector(("Not A Tab",)) == ""
