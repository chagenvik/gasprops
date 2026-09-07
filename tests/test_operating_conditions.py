from pathlib import Path
import inspect
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import gasprop.operating_conditions as oc
from gasprop.views import dp_flow as dp_flow_view
from gasprop.views import flow_converter as flow_converter_view
from gasprop.views import multi as multi_view
from gasprop.views import single as single_view
from gasprop.views import uncertainty as uncertainty_view


# ── Unit helpers ──────────────────────────────────────────────────────────────
def test_temperature_label_maps_celsius_and_kelvin():
    assert oc.temperature_label("C") == "°C"
    assert oc.temperature_label("K") == "K"


def test_temperature_floor_is_absolute_zero_in_each_unit():
    assert oc.temperature_floor("C") == pytest.approx(-273.15)
    assert oc.temperature_floor("K") == pytest.approx(0.0)


def test_supported_units_and_equations():
    assert oc.PRESSURE_UNITS == ("bara", "barg", "kPa", "MPa")
    assert oc.TEMPERATURE_UNITS == ("C", "K")
    assert oc.AGA8_EQUATIONS == ("GERG-2008", "DETAIL")


# ── Layout ordering ───────────────────────────────────────────────────────────
def test_pressure_input_renders_the_value_before_the_unit():
    # The value must go in the left column and the unit in the right, even though the
    # unit is read first so it can appear in the value's label.
    source = inspect.getsource(oc.pressure_input)
    assert source.index("value_col, unit_col = st.columns") < source.index("unit_col.selectbox")
    assert "value_col.number_input" in source


def test_temperature_input_renders_the_value_before_the_unit():
    source = inspect.getsource(oc.temperature_input)
    assert source.index("value_col, unit_col = st.columns") < source.index("unit_col.selectbox")
    assert "value_col.number_input" in source


def test_temperature_input_floor_follows_the_selected_unit():
    source = inspect.getsource(oc.temperature_input)
    assert "temperature_floor(str(unit))" in source


def _render_source(view_module, function_name: str = "render") -> str:
    return inspect.getsource(getattr(view_module, function_name))


@pytest.mark.parametrize(
    "view_module, function_name, equation_key",
    [
        (single_view, "render", "single_eos"),
        (flow_converter_view, "render", "fc_eos"),
        (dp_flow_view, "_render_single_point", "dpf_eos_single"),
        (dp_flow_view, "_render_sizing", "dpf_eos_sizing"),
    ],
)
def test_scalar_views_order_pressure_then_temperature_then_equation(
    view_module, function_name, equation_key
):
    source = _render_source(view_module, function_name)

    pressure_at = source.index("pressure_input(")
    temperature_at = source.index("temperature_input(")
    equation_at = source.index("aga8_equation_input(")

    assert pressure_at < temperature_at < equation_at
    assert equation_key in source


def test_uncertainty_view_puts_the_equation_after_the_conditions():
    source = _render_source(uncertainty_view)

    assert source.index("pressure_input(") < source.index("aga8_equation_input(")
    assert source.index("temperature_input(") < source.index("aga8_equation_input(")


def test_multi_view_puts_the_equation_after_the_unit_selectors():
    source = _render_source(multi_view)

    assert source.index('"Pressure unit"') < source.index("aga8_equation_input(")
    assert source.index('"Temperature unit"') < source.index("aga8_equation_input(")


def test_dp_flow_unit_inputs_put_the_equation_last():
    source = inspect.getsource(dp_flow_view._unit_inputs)

    assert source.index('"Pressure unit"') < source.index("aga8_equation_input(")
    assert source.index('"Temperature unit"') < source.index("aga8_equation_input(")


# ── No view re-implements the layout by hand ──────────────────────────────────
@pytest.mark.parametrize(
    "view_module, function_name",
    [
        (single_view, "render"),
        (flow_converter_view, "render"),
        (dp_flow_view, "_render_single_point"),
        (dp_flow_view, "_render_sizing"),
    ],
)
def test_scalar_views_do_not_hand_roll_the_unit_selectors(view_module, function_name):
    source = _render_source(view_module, function_name)

    assert '"Pressure unit"' not in source
    assert '"Temperature unit"' not in source


@pytest.mark.parametrize(
    "view_module",
    [single_view, flow_converter_view, dp_flow_view, uncertainty_view, multi_view],
)
def test_views_do_not_hard_code_the_aga8_equation_list(view_module):
    source = inspect.getsource(view_module)
    assert '["GERG-2008", "DETAIL"]' not in source


def test_session_state_keys_stay_unique_within_the_dp_flow_sub_tabs():
    # The three DP sub-tabs share one page, so their widget keys must not collide.
    # \b prevents `key=` from also matching inside `unit_key=` / `value_key=`.
    pattern = re.compile(r'\b(?:key|unit_key|value_key)="([^"]+)"')
    keys: list[str] = []
    for name in ("_render_single_point", "_render_sizing", "_render_multi_point"):
        keys.extend(pattern.findall(inspect.getsource(getattr(dp_flow_view, name))))

    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    assert duplicates == []


def test_dp_flow_sub_tabs_each_have_their_own_pressure_and_equation_keys():
    pattern = re.compile(r'\b(?:key|unit_key|value_key)="([^"]+)"')
    single = set(pattern.findall(inspect.getsource(dp_flow_view._render_single_point)))
    sizing = set(pattern.findall(inspect.getsource(dp_flow_view._render_sizing)))

    assert "dpf_pressure_single" in single
    assert "dpf_pressure_sizing" in sizing
    assert single.isdisjoint(sizing)
