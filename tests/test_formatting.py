from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gasprop.formatting import (
    NOT_AVAILABLE,
    format_fixed,
    format_flow,
    format_value,
    format_velocity,
)


# ── The complaints that motivated this formatter ──────────────────────────────
def test_beta_of_exactly_0_6_does_not_print_six_decimals():
    # Regression guard: this used to render as "0.600000".
    assert format_value(0.6) == "0.6"


def test_dimensionless_coefficients_keep_their_meaningful_digits():
    assert format_value(0.603627) == "0.603627"
    assert format_value(0.997539) == "0.997539"


def test_large_flow_rates_lose_meaningless_decimals():
    assert format_value(58736.1044) == "58,736.1"
    assert format_value(1873349.93) == "1,873,350"


def test_reynolds_number_reads_as_a_plain_number_not_scientific():
    assert format_value(8206300.0) == "8,206,300"


def test_differential_pressure_of_exactly_500_prints_cleanly():
    assert format_value(500.0) == "500"


# ── Significant digits ────────────────────────────────────────────────────────
def test_six_significant_digits_are_kept_across_magnitudes():
    assert format_value(1175.6629) == "1,175.66"
    assert format_value(10.3951) == "10.3951"
    assert format_value(1.23456789) == "1.23457"


def test_leading_zeros_do_not_count_as_significant_digits():
    assert format_value(0.0109) == "0.0109"
    assert format_value(0.00123456789) == "0.00123457"


def test_significant_digit_count_is_configurable():
    assert format_value(1.23456789, significant=3) == "1.23"
    assert format_value(1234.5678, significant=3) == "1,235"


# ── Thousands separators ──────────────────────────────────────────────────────
def test_thousands_separators_are_applied():
    assert format_value(1234567.0) == "1,234,567"
    assert format_value(999.0) == "999"


# ── Extremes ──────────────────────────────────────────────────────────────────
def test_very_large_numbers_switch_to_scientific_notation():
    assert format_value(1.5e10) == "1.5000e+10"


def test_very_small_numbers_switch_to_scientific_notation():
    assert format_value(1.2e-5) == "1.2000e-05"
    assert format_value(9.87654e-9) == "9.8765e-09"


def test_the_scientific_thresholds_are_the_documented_ones():
    # Just inside the linear range on both ends.
    assert "e" not in format_value(9.99e8)
    assert "e" not in format_value(1.01e-4)


def test_zero_is_a_bare_zero():
    assert format_value(0.0) == "0"


def test_negative_numbers_keep_their_sign():
    assert format_value(-273.15) == "-273.15"
    assert format_value(-0.6) == "-0.6"


# ── Missing values ────────────────────────────────────────────────────────────
def test_none_formats_as_the_not_available_dash():
    assert format_value(None) == NOT_AVAILABLE


def test_nan_and_infinity_format_as_the_not_available_dash():
    assert format_value(float("nan")) == NOT_AVAILABLE
    assert format_value(float("inf")) == NOT_AVAILABLE
    assert format_value(float("-inf")) == NOT_AVAILABLE


def test_non_numeric_input_formats_as_the_not_available_dash():
    assert format_value("not a number") == NOT_AVAILABLE


def test_integers_are_accepted():
    assert format_value(42) == "42"


# ── No trailing separator artefacts ───────────────────────────────────────────
@pytest.mark.parametrize(
    "value",
    [0.6, 2000.0, 500.0, 1.0, 0.5, 123456.0, 0.001, 7.0],
)
def test_formatted_values_never_end_with_a_dot(value):
    assert not format_value(value).endswith(".")


# ── Flow rates: one decimal, whatever the magnitude ───────────────────────────
def test_flow_rates_keep_one_decimal_across_magnitudes():
    assert format_flow(205344.2712) == "205,344.3"
    assert format_flow(2621.7912) == "2,621.8"
    assert format_flow(302056.44) == "302,056.4"
    assert format_flow(7249335.2) == "7,249,335.2"


def test_flow_rate_decimal_is_kept_for_round_numbers():
    # Regression guard: the significant-digit formatter rendered this as "2,000".
    assert format_flow(2000.0) == "2,000.0"


def test_zero_flow_still_shows_the_decimal():
    assert format_flow(0.0) == "0.0"


def test_small_flow_rates_keep_their_resolution_instead_of_rounding_to_zero():
    assert format_flow(0.0123) == "0.0123"
    assert format_flow(-0.0123) == "-0.0123"


# ── Velocities: two decimals ──────────────────────────────────────────────────
def test_velocities_keep_two_decimals():
    assert format_velocity(23.1817) == "23.18"
    assert format_velocity(7.0) == "7.00"
    assert format_velocity(1234.5678) == "1,234.57"


def test_zero_velocity_shows_two_decimals():
    assert format_velocity(0.0) == "0.00"


def test_small_velocities_keep_their_resolution_instead_of_rounding_to_zero():
    assert format_velocity(0.0001234) == "0.0001234"


# ── Fixed-decimal formatting in general ───────────────────────────────────────
def test_the_number_of_decimals_is_configurable():
    assert format_fixed(23.1817, 0) == "23"
    assert format_fixed(23.1817, 3) == "23.182"


def test_negative_values_never_render_as_a_signed_zero():
    assert format_fixed(-0.0, 1) == "0.0"


def test_fixed_formatting_of_missing_and_non_finite_values():
    assert format_fixed(None, 1) == NOT_AVAILABLE
    assert format_fixed(float("nan"), 1) == NOT_AVAILABLE
    assert format_fixed(float("inf"), 2) == NOT_AVAILABLE
    assert format_fixed("not a number", 1) == NOT_AVAILABLE
    assert format_flow(None) == NOT_AVAILABLE
    assert format_velocity(None) == NOT_AVAILABLE
