"""Shared helpers for canonical composition CSV import/export."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
import re
from typing import IO, Any, Iterable

import pandas as pd

CANONICAL_COLUMNS = ("Component", "MolePercent", "MW", "Dens")
DEFAULT_REQUIRED_COLUMNS = CANONICAL_COLUMNS

LEGACY_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "Component": ("Component",),
    "MolePercent": ("MolePercent", "Mol %", "Mol%", "Mole%"),
    "MW": ("MW", "MW [g/mol]", "MW (kg/kmol)"),
    "Dens": ("Dens", "Density [kg/m³]", "Density (kg/m³)"),
}

OPTIONAL_IMPORT_COLUMNS = frozenset({"Name"})

DEFINED_TO_PSEUDO_HEAVY = {
    "nC6": "C6",
    "nC7": "C7",
    "nC8": "C8",
    "nC9": "C9",
    "nC10": "C10",
}
PSEUDO_TO_DEFINED_HEAVY = {value: key for key, value in DEFINED_TO_PSEUDO_HEAVY.items()}

_UNNAMED_COLUMN_RE = re.compile(r"^Unnamed:\s*\d+$", re.IGNORECASE)
_PLUS_COMPONENT_RE = re.compile(r"^C(?P<carbon>\d+)\+?$", re.IGNORECASE)
_CHARACTERIZED_COMPONENT_RE = re.compile(r"^C\d+\s*-\s*C?\d+\+?$", re.IGNORECASE)
_COLUMN_ALIAS_LOOKUP = {
    alias: canonical
    for canonical, aliases in LEGACY_COLUMN_ALIASES.items()
    for alias in aliases
}


class CompositionCSVError(ValueError):
    """Raised when a composition CSV cannot be normalized or validated."""


class CompositionFluidType(str, Enum):
    CHARACTERIZED = "CHARACTERIZED"
    PLUS = "PLUS"
    NO_PLUS = "NO_PLUS"


def normalize_component_name(component_name: Any) -> str:
    return str(component_name).strip()


def to_pseudo_heavy_component_name(component_name: Any) -> str:
    component_name = normalize_component_name(component_name)
    return DEFINED_TO_PSEUDO_HEAVY.get(component_name, component_name)


def to_defined_heavy_component_name(component_name: Any) -> str:
    component_name = normalize_component_name(component_name)
    return PSEUDO_TO_DEFINED_HEAVY.get(component_name, component_name)


def is_plus_component_name(component_name: Any) -> bool:
    component_name = normalize_component_name(component_name)
    if component_name in DEFINED_TO_PSEUDO_HEAVY:
        return False
    match = _PLUS_COMPONENT_RE.match(component_name)
    return bool(match and int(match.group("carbon")) >= 6)


def is_characterized_component_name(component_name: Any) -> bool:
    return bool(_CHARACTERIZED_COMPONENT_RE.match(normalize_component_name(component_name)))


def normalize_composition_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cleaned_original_names = {normalize_component_name(column) for column in df.columns}

    rename_map: dict[str, str] = {}
    drop_columns: list[str] = []

    for column in df.columns:
        cleaned_name = normalize_component_name(column)

        if (
            cleaned_name in OPTIONAL_IMPORT_COLUMNS
            or cleaned_name == ""
            or _UNNAMED_COLUMN_RE.match(cleaned_name)
        ):
            drop_columns.append(column)
            continue

        canonical_name = _COLUMN_ALIAS_LOOKUP.get(cleaned_name, cleaned_name)

        if cleaned_name != canonical_name and canonical_name in cleaned_original_names:
            drop_columns.append(column)
            continue

        rename_map[column] = canonical_name

    normalized = df.drop(columns=drop_columns).rename(columns=rename_map)
    return normalized


def validate_composition_columns(
    df: pd.DataFrame,
    required_columns: Iterable[str] = DEFAULT_REQUIRED_COLUMNS,
) -> None:
    required_columns = tuple(required_columns)
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        available_columns = ", ".join(str(column) for column in df.columns) or "<none>"
        missing = ", ".join(missing_columns)
        raise CompositionCSVError(
            f"Composition CSV is missing required columns: {missing}. "
            f"Available columns after normalization: {available_columns}. "
            f"Expected canonical columns use the schema: {', '.join(CANONICAL_COLUMNS)}."
        )


def canonicalize_heavy_component_names(
    df: pd.DataFrame,
    *,
    target: str = "keep",
) -> pd.DataFrame:
    if "Component" not in df.columns:
        return df.copy()

    if target not in {"keep", "pseudo", "defined"}:
        raise ValueError("target must be one of: 'keep', 'pseudo', 'defined'.")

    normalized = df.copy()
    if target == "pseudo":
        normalized["Component"] = normalized["Component"].map(to_pseudo_heavy_component_name)
    elif target == "defined":
        normalized["Component"] = normalized["Component"].map(to_defined_heavy_component_name)

    return normalized


def _values_match(left: Any, right: Any) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True

    try:
        return abs(float(left) - float(right)) <= 1e-9
    except (TypeError, ValueError):
        return left == right


def _first_non_null(values: pd.Series) -> Any:
    for value in values:
        if pd.notna(value):
            return value
    return pd.NA


def _distinct_non_null_values(values: pd.Series) -> list[Any]:
    distinct: list[Any] = []
    for value in values:
        if pd.isna(value):
            continue
        if not any(_values_match(value, existing) for existing in distinct):
            distinct.append(value)
    return distinct


def handle_lossy_heavy_component_conversion(
    df: pd.DataFrame,
    *,
    target: str = "keep",
    sum_columns: Iterable[str] = ("MolePercent",),
    validate_equal_columns: Iterable[str] = (),
) -> tuple[pd.DataFrame, list[str]]:
    if "Component" not in df.columns:
        return df.copy(), []

    if target not in {"keep", "pseudo", "defined"}:
        raise ValueError("target must be one of: 'keep', 'pseudo', 'defined'.")

    converted = df.copy()
    converted["Component"] = converted["Component"].map(normalize_component_name)
    if target == "keep":
        return converted, []

    converter = (
        to_pseudo_heavy_component_name
        if target == "pseudo"
        else to_defined_heavy_component_name
    )

    source_components = converted["Component"].copy()
    converted["Component"] = source_components.map(converter)
    converted["_SourceComponent"] = source_components

    warnings: list[str] = []
    for component_name, group in converted.groupby("Component", sort=False, dropna=False):
        source_names = list(dict.fromkeys(group["_SourceComponent"].tolist()))
        if all(source_name == component_name for source_name in source_names):
            continue

        if len(source_names) == 1:
            warnings.append(
                f"Converted {source_names[0]} to {component_name}. "
                "C6..C10 and nC6..nC10 are not fully interchangeable, so this import is lossy."
            )
        else:
            warnings.append(
                f"Merged {', '.join(source_names)} into {component_name}. "
                "C6..C10 and nC6..nC10 are not fully interchangeable, so this import is lossy."
            )

    if not converted["Component"].duplicated(keep=False).any():
        return converted.drop(columns="_SourceComponent"), warnings

    sum_columns = set(sum_columns)
    validate_equal_columns = set(validate_equal_columns)
    rows: list[dict[str, Any]] = []

    for component_name, group in converted.groupby("Component", sort=False, dropna=False):
        merged_row: dict[str, Any] = {"Component": component_name}
        source_names = list(dict.fromkeys(group["_SourceComponent"].tolist()))

        for column in df.columns:
            if column == "Component":
                continue

            values = group[column]
            if column in sum_columns:
                merged_row[column] = float(pd.to_numeric(values, errors="coerce").fillna(0.0).sum())
                continue

            if column in validate_equal_columns:
                distinct_values = _distinct_non_null_values(values)
                if len(distinct_values) > 1:
                    raise CompositionCSVError(
                        f"Cannot safely merge {', '.join(source_names)} into {component_name}: "
                        f"conflicting {column} values {distinct_values}."
                    )
                merged_row[column] = distinct_values[0] if distinct_values else _first_non_null(values)
                continue

            merged_row[column] = _first_non_null(values)

        rows.append(merged_row)

    return pd.DataFrame(rows, columns=df.columns), warnings


def _coerce_composition_dataframe(data: Any) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data.copy()

    to_dataframe = getattr(data, "to_dataframe", None)
    if callable(to_dataframe):
        return pd.DataFrame(to_dataframe())

    if isinstance(data, (str, Path)):
        return pd.read_csv(data)

    if hasattr(data, "read"):
        return pd.read_csv(data)

    return pd.DataFrame(data)


def canonicalize_composition_dataframe(
    data: Any,
    *,
    required_columns: Iterable[str] = DEFAULT_REQUIRED_COLUMNS,
    heavy_component_names: str = "keep",
) -> pd.DataFrame:
    df = normalize_composition_columns(_coerce_composition_dataframe(data))
    validate_composition_columns(df, required_columns=required_columns)

    canonical_columns = [column for column in CANONICAL_COLUMNS if column in df.columns]
    canonical_df = df.loc[:, canonical_columns].copy()
    if "Component" in canonical_df.columns:
        canonical_df["Component"] = canonical_df["Component"].map(normalize_component_name)

    return canonicalize_heavy_component_names(
        canonical_df,
        target=heavy_component_names,
    )


def read_composition_csv(
    source: str | Path | IO[str] | IO[bytes],
    *,
    required_columns: Iterable[str] = DEFAULT_REQUIRED_COLUMNS,
    heavy_component_names: str = "keep",
) -> pd.DataFrame:
    return canonicalize_composition_dataframe(
        source,
        required_columns=required_columns,
        heavy_component_names=heavy_component_names,
    )


def detect_fluid_type(data: Any) -> CompositionFluidType:
    if (
        isinstance(data, pd.DataFrame)
        or hasattr(data, "to_dataframe")
        or isinstance(data, (str, Path))
        or hasattr(data, "read")
    ):
        df = canonicalize_composition_dataframe(data, required_columns=("Component",), heavy_component_names="keep")
        component_names = df["Component"].tolist()
    else:
        component_names = [normalize_component_name(component_name) for component_name in data]

    if any(is_characterized_component_name(component_name) for component_name in component_names):
        return CompositionFluidType.CHARACTERIZED

    if any(is_plus_component_name(component_name) for component_name in component_names):
        return CompositionFluidType.PLUS

    return CompositionFluidType.NO_PLUS


def to_pvtcalc_fluid_type(fluid_type: CompositionFluidType | str):
    from pvtcalc.settings import FluidType

    return FluidType[CompositionFluidType(fluid_type).name]


def export_canonical_composition_dataframe(
    data: Any,
    *,
    heavy_component_names: str = "keep",
) -> pd.DataFrame:
    return canonicalize_composition_dataframe(
        data,
        required_columns=CANONICAL_COLUMNS,
        heavy_component_names=heavy_component_names,
    )


def export_canonical_composition_csv(
    data: Any,
    *,
    heavy_component_names: str = "keep",
) -> str:
    canonical_df = export_canonical_composition_dataframe(
        data,
        heavy_component_names=heavy_component_names,
    )
    return canonical_df.to_csv(index=False, lineterminator="\n")
