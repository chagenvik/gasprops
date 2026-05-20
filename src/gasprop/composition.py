from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Iterable

import pandas as pd

from .constants import COMPONENTS, COMPONENT_ALIASES, DEFAULT_EXAMPLE


EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "examples"
CANONICAL_COLUMNS = ["Component", "MolePercent", "MW", "Dens"]


def canonical_component_name(raw: str) -> str:
    """Normalize a raw component label to the app's standard internal name."""
    key = str(raw).strip()
    normalized = key.lower().replace(" ", "").replace("-", "")
    if normalized in COMPONENT_ALIASES:
        return COMPONENT_ALIASES[normalized]
    if key in COMPONENTS:
        return key
    upper = key.upper().replace(" ", "")
    if upper in COMPONENTS:
        return upper
    return key


def normalize_composition(values: dict[str, float]) -> dict[str, float]:
    """Normalize component values to a 100 mol% composition."""
    cleaned = {canonical_component_name(k): float(v) for k, v in values.items() if float(v) > 0}
    total = sum(cleaned.values())
    if total <= 0:
        return {name: 0.0 for name in COMPONENTS}
    normalized = {name: 0.0 for name in COMPONENTS}
    for name, value in cleaned.items():
        if name in normalized:
            normalized[name] = value * 100.0 / total
    return {name: normalized[name] for name in COMPONENTS}


def composition_from_dict(values: dict[str, float]) -> pd.DataFrame:
    """Build a canonical composition table from component values."""
    normalized = normalize_composition(values)
    rows = []
    for name, spec in COMPONENTS.items():
        mole_percent = float(normalized.get(name, 0.0))
        rows.append(
            {
                "Component": name,
                "MolePercent": mole_percent,
                "MW": spec.mw_g_mol,
                "Dens": None,
            }
        )
    return pd.DataFrame(rows, columns=CANONICAL_COLUMNS)


def dict_from_composition_frame(frame: pd.DataFrame) -> dict[str, float]:
    """Extract a normalized composition from a table."""
    if frame.empty:
        return {name: 0.0 for name in COMPONENTS}
    if "Component" not in frame.columns:
        raise ValueError("Composition table needs a Component column")
    mole_column = next((c for c in frame.columns if c.lower().replace(" ", "") in {"molepercent", "mol%", "mole%"}), None)
    if mole_column is None:
        raise ValueError("Composition table needs a MolePercent column")
    values = {}
    for _, row in frame.iterrows():
        name = canonical_component_name(row["Component"])
        if name not in COMPONENTS:
            continue
        value = float(row[mole_column] or 0.0)
        if value > 0:
            values[name] = value
    normalized = normalize_composition(values)
    return normalized


def composition_to_csv(values: dict[str, float]) -> str:
    """Serialize a composition to canonical CSV text."""
    return composition_from_dict(values).to_csv(index=False)


def frame_from_csv_text(text: str) -> pd.DataFrame:
    """Read a composition CSV into a DataFrame."""
    return pd.read_csv(StringIO(text))


def composition_from_csv_text(text: str) -> dict[str, float]:
    """Parse a composition CSV into normalized values."""
    return dict_from_composition_frame(frame_from_csv_text(text))


def available_example_names() -> list[str]:
    """Return the available example composition names."""
    if EXAMPLE_DIR.exists():
        preferred = [
            "lean_gas",
            "rich_gas_01",
            "rich_gas_02",
            "rich_gas_03",
            "rich_gas_04",
            "hydrogen_blend",
        ]
        available = {path.stem for path in EXAMPLE_DIR.glob("*.csv")}
        ordered = [name for name in preferred if name in available]
        ordered.extend(sorted(available - set(ordered)))
        return ordered
    return []


def load_example_composition(name: str) -> dict[str, float]:
    """Load an example composition by name."""
    if EXAMPLE_DIR.exists():
        path = EXAMPLE_DIR / f"{name}.csv"
        if path.exists():
            return composition_from_csv_text(path.read_text())
    raise KeyError(name)


def composition_label(values: dict[str, float]) -> str:
    """Build a short label for the largest composition components."""
    nonzero = [(k, v) for k, v in values.items() if v > 0]
    if not nonzero:
        return "Empty composition"
    top = sorted(nonzero, key=lambda item: item[1], reverse=True)[:4]
    return ", ".join(f"{name} {value:.1f}%" for name, value in top)


def composition_percent_sum(values: dict[str, float]) -> float:
    """Return the total composition in mol%."""
    return sum(float(v) for v in values.values())


def composition_to_mole_fractions(values: dict[str, float]) -> dict[str, float]:
    """Convert mol% values to mole fractions."""
    total = composition_percent_sum(values)
    if total <= 0:
        return {name: 0.0 for name in COMPONENTS}
    return {name: float(values.get(name, 0.0)) / total for name in COMPONENTS}


def fill_missing_components(values: dict[str, float]) -> dict[str, float]:
    """Return a full composition mapping with missing components set to zero."""
    normalized = normalize_composition(values)
    return {name: float(normalized.get(name, 0.0)) for name in COMPONENTS}

