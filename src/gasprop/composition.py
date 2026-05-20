from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Iterable

import pandas as pd

from .constants import COMPONENTS, COMPONENT_ALIASES, DEFAULT_EXAMPLE, EXAMPLE_COMPOSITIONS


EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "examples"
CANONICAL_COLUMNS = ["Component", "MolePercent", "MW", "Dens"]


def canonical_component_name(raw: str) -> str:
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
    return composition_from_dict(values).to_csv(index=False)


def frame_from_csv_text(text: str) -> pd.DataFrame:
    return pd.read_csv(StringIO(text))


def composition_from_csv_text(text: str) -> dict[str, float]:
    return dict_from_composition_frame(frame_from_csv_text(text))


def available_example_names() -> list[str]:
    preferred = [
        "lean_gas",
        "rich_gas_01",
        "rich_gas_02",
        "rich_gas_03",
        "rich_gas_04",
        "hydrogen_blend",
    ]
    names = [name for name in preferred if name in EXAMPLE_COMPOSITIONS]
    if EXAMPLE_DIR.exists():
        available_files = {path.stem for path in EXAMPLE_DIR.glob("*.csv")}
        names.extend([name for name in preferred if name in available_files and name not in names])
        names.extend(sorted((available_files | set(EXAMPLE_COMPOSITIONS)) - set(names)))
    return names


def load_example_composition(name: str) -> dict[str, float]:
    if EXAMPLE_DIR.exists():
        path = EXAMPLE_DIR / f"{name}.csv"
        if path.exists():
            return composition_from_csv_text(path.read_text())
    if name in EXAMPLE_COMPOSITIONS:
        return normalize_composition(EXAMPLE_COMPOSITIONS[name])
    if name == DEFAULT_EXAMPLE:
        return normalize_composition(EXAMPLE_COMPOSITIONS[DEFAULT_EXAMPLE])
    raise KeyError(name)


def composition_label(values: dict[str, float]) -> str:
    nonzero = [(k, v) for k, v in values.items() if v > 0]
    if not nonzero:
        return "Empty composition"
    top = sorted(nonzero, key=lambda item: item[1], reverse=True)[:4]
    return ", ".join(f"{name} {value:.1f}%" for name, value in top)


def composition_percent_sum(values: dict[str, float]) -> float:
    return sum(float(v) for v in values.values())


def composition_to_mole_fractions(values: dict[str, float]) -> dict[str, float]:
    total = composition_percent_sum(values)
    if total <= 0:
        return {name: 0.0 for name in COMPONENTS}
    return {name: float(values.get(name, 0.0)) / total for name in COMPONENTS}


def fill_missing_components(values: dict[str, float]) -> dict[str, float]:
    normalized = normalize_composition(values)
    return {name: float(normalized.get(name, 0.0)) for name in COMPONENTS}

