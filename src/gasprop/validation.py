from __future__ import annotations

from dataclasses import dataclass

from .constants import VALIDATION_LIMITS


@dataclass(frozen=True)
class ValidationIssue:
    category: str
    name: str
    message: str
    severity: str = "warning"


def validate_composition(values: dict[str, float], mode: str = "GERG-2008") -> list[ValidationIssue]:
    limits = VALIDATION_LIMITS[mode]["components"]
    issues: list[ValidationIssue] = []
    total = sum(float(v) for v in values.values())
    if abs(total - 100.0) > 0.1:
        issues.append(ValidationIssue("composition", "TOTAL", f"Composition sums to {total:.3f}%, expected 100.0%", "warning"))
    for name, (low, high) in limits.items():
        value = float(values.get(name, 0.0))
        if value < low - 1e-9 or value > high + 1e-9:
            issues.append(ValidationIssue("composition", name, f"{name} = {value:.3f}% is outside {low:.3f}%–{high:.3f}%", "warning"))
    return issues


def validate_state(pressure_bar: float, temperature_c: float, mode: str = "GERG-2008") -> list[ValidationIssue]:
    limits = VALIDATION_LIMITS[mode]
    issues: list[ValidationIssue] = []
    if pressure_bar > limits["pressure_bar"]:
        issues.append(ValidationIssue("state", "PRESSURE", f"Pressure {pressure_bar:.2f} bar exceeds {limits['pressure_bar']:.2f} bar", "warning"))
    if temperature_c > limits["temperature_c"]:
        issues.append(ValidationIssue("state", "TEMPERATURE", f"Temperature {temperature_c:.2f} °C exceeds {limits['temperature_c']:.2f} °C", "warning"))
    return issues


def is_in_range(values: dict[str, float], pressure_bar: float, temperature_c: float, mode: str = "GERG-2008") -> bool:
    return not validate_composition(values, mode) and not validate_state(pressure_bar, temperature_c, mode)

