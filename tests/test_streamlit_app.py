from pathlib import Path
import sys
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_invalid_surface_range_does_not_hide_later_tabs():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180).run()

    at.number_input(key="surf_p_min").set_value(200.0)
    at.number_input(key="surf_p_max").set_value(100.0)
    at.button(key="surf_gen_btn").click()
    at.run()

    assert [error.value for error in at.error if "Pressure min" in error.value] == [
        "Pressure min must be less than max."
    ]
    assert at.button(key="fc_convert").key == "fc_convert"


def test_very_large_surface_range_is_rejected_before_allocating_grid():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180).run()

    at.number_input(key="surf_p_max").set_value(1e308)
    at.button(key="surf_gen_btn").click()
    at.run()

    assert [error.value for error in at.error if "Grid too large" in error.value] == [
        "Grid too large (unsafe). Reduce the range or increase the step size."
    ]
    assert not at.exception
    assert at.button(key="fc_convert").key == "fc_convert"


def test_zero_absolute_pressure_shows_error_without_crashing_app():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180).run()

    at.number_input(key="single_pressure").set_value(0.0)
    at.button(key="single_calc_btn").click()
    at.run()

    assert [error.value for error in at.error if "absolute-pressure" in error.value] == [
        "Pressure must be finite and greater than zero on an absolute-pressure basis."
    ]
    assert not at.exception
    assert at.button(key="fc_convert").key == "fc_convert"


def test_including_klab_gases_does_not_mix_widget_defaults_with_session_state(caplog):
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180).run()
    caplog.clear()

    at.checkbox(key="aga8_refprop_include_klab").set_value(True)
    at.run()

    assert at.checkbox(key="aga8_refprop_fix_y").value is True
    assert at.number_input(key="aga8_refprop_ymin").value == -1.3
    assert at.number_input(key="aga8_refprop_ymax").value == 1.3
    assert not any(
        "created with a default value but also had its value set" in record.message
        for record in caplog.records
    )


def test_cricondentherm_comparison_result_survives_next_rerun():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180).run()
    at.slider(key="ecmp_n_pts").set_value(20)

    fake_grid = {
        f"{prop}_{equation}": [1.0] * 20
        for prop in ("rho", "z", "w", "kappa", "cp", "cv", "h", "s", "u", "g", "jt", "mm")
        for equation in ("gerg", "detail")
    }
    with (
        patch("gasprop.views.comparison._calc_cricondentherm", return_value=-50.0),
        patch("gasprop.views.comparison._run_grid", return_value=fake_grid),
    ):
        at.button(key="ecmp_run_btn").click()
        at.run()
        result_key = at.session_state["gp_eos_cmp_grid"]["key"]

        at.run()

    assert at.session_state["gp_eos_cmp_grid"]["key"] == result_key
    assert any(
        "Relative deviation: DETAIL vs GERG-2008" in markdown.value
        for markdown in at.markdown
    )


def test_uncertainty_results_are_hidden_after_an_input_changes():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180).run()

    at.button(key="unc_run_std").click()
    at.run()
    assert any(
        "Standard Uncertainty Results" in markdown.value for markdown in at.markdown
    )

    at.number_input(key="unc_p_mean").set_value(110.0)
    at.run()

    assert not any(
        "Standard Uncertainty Results" in markdown.value for markdown in at.markdown
    )
    assert any(
        "Uncertainty inputs changed" in info.value for info in at.info
    )
