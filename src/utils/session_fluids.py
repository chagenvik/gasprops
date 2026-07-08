"""Per-session in-memory fluid library shared across the app."""

from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from typing import Iterable
from uuid import uuid4

import pandas as pd
import streamlit as st

from utils.composition_csv import (
    CANONICAL_COLUMNS,
    canonicalize_composition_dataframe,
    export_canonical_composition_csv,
)

SESSION_FLUIDS_KEY = "session_temp_fluids"
MAX_SESSION_FLUIDS = 20
FORMAT_PVTCALC = "pvtcalc"
FORMAT_AGA8 = "aga8"
_VALID_FORMATS = frozenset({FORMAT_PVTCALC, FORMAT_AGA8})

AGA8_COMPONENTS: tuple[str, ...] = (
    "N2", "CO2", "C1", "C2", "C3",
    "iC4", "nC4", "iC5", "nC5",
    "nC6", "nC7", "nC8", "nC9", "nC10",
    "H2O", "He", "H2", "Ar", "CO", "O2", "H2S",
)
_AGA8_COMPONENTS_SET = frozenset(AGA8_COMPONENTS)

PSEUDO_TO_AGA8_HEAVY: dict[str, str] = {
    "C6": "nC6",
    "C7": "nC7",
    "C8": "nC8",
    "C9": "nC9",
    "C10": "nC10",
}


@dataclass
class SessionFluid:
    id: str
    display_name: str
    format_family: str
    canonical_csv: str
    source_module: str
    source_context: str = ""
    tags: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)


@dataclass
class Aga8ConversionResult:
    canonical_csv: str
    assignments: tuple[tuple[str, str], ...]
    removed: tuple[str, ...]


class SessionFluidLimitError(RuntimeError):
    pass


def _registry() -> list[SessionFluid]:
    if SESSION_FLUIDS_KEY not in st.session_state:
        st.session_state[SESSION_FLUIDS_KEY] = []
    return st.session_state[SESSION_FLUIDS_KEY]


def _replace_registry(fluids: list[SessionFluid]) -> None:
    st.session_state[SESSION_FLUIDS_KEY] = fluids


def list_session_fluids(*, format_family: str | None = None) -> list[SessionFluid]:
    fluids = list(_registry())
    if format_family is not None:
        fluids = [f for f in fluids if f.format_family == format_family]
    return fluids


def get_session_fluid(fluid_id: str) -> SessionFluid | None:
    for fluid in _registry():
        if fluid.id == fluid_id:
            return fluid
    return None


def remove_session_fluid(fluid_id: str) -> bool:
    fluids = _registry()
    for index, fluid in enumerate(fluids):
        if fluid.id == fluid_id:
            del fluids[index]
            return True
    return False


def rename_session_fluid(fluid_id: str, new_name: str) -> bool:
    new_name = (new_name or "").strip()
    if not new_name:
        return False
    fluids = _registry()
    existing = {f.display_name for f in fluids if f.id != fluid_id}
    final_name = _disambiguate_name(new_name, existing)
    for fluid in fluids:
        if fluid.id == fluid_id:
            fluid.display_name = final_name
            return True
    return False


def clear_session_fluids() -> None:
    _replace_registry([])


def save_session_fluid(
    *,
    canonical_csv: str,
    format_family: str,
    source_module: str,
    base_name: str,
    source_context: str = "",
    tags: Iterable[str] = (),
) -> SessionFluid:
    if format_family not in _VALID_FORMATS:
        raise ValueError(
            f"Unknown composition format family: {format_family!r}. "
            f"Expected one of: {', '.join(sorted(_VALID_FORMATS))}."
        )
    if not canonical_csv or not canonical_csv.strip():
        raise ValueError("Cannot save an empty composition.")

    fluids = list(_registry())
    if len(fluids) >= MAX_SESSION_FLUIDS:
        raise SessionFluidLimitError(
            f"Session fluid library is full ({MAX_SESSION_FLUIDS} entries). "
            "Delete an existing saved fluid before saving a new one."
        )

    existing_names = {f.display_name for f in fluids}
    display_name = _disambiguate_name(base_name.strip() or "Saved fluid", existing_names)

    fluid = SessionFluid(
        id=uuid4().hex,
        display_name=display_name,
        format_family=format_family,
        canonical_csv=canonical_csv,
        source_module=source_module,
        source_context=source_context,
        tags=tuple(tags),
    )
    _replace_registry([*fluids, fluid])
    return fluid


def save_pvtcalc_composition(
    composition,
    *,
    source_module: str,
    base_name: str,
    source_context: str = "",
    tags: Iterable[str] = (),
) -> SessionFluid:
    canonical_csv = export_canonical_composition_csv(composition)
    return save_session_fluid(
        canonical_csv=canonical_csv,
        format_family=FORMAT_PVTCALC,
        source_module=source_module,
        base_name=base_name,
        source_context=source_context,
        tags=tags,
    )


def convert_pvtcalc_to_aga8(canonical_csv: str) -> Aga8ConversionResult:
    df = canonicalize_composition_dataframe(
        io.StringIO(canonical_csv),
        required_columns=("Component", "MolePercent"),
        heavy_component_names="keep",
    )

    assignments: list[tuple[str, str]] = []
    removed: list[str] = []
    rows: dict[str, dict[str, float]] = {}
    seen_assignments: set[tuple[str, str]] = set()

    for _, row in df.iterrows():
        original = str(row["Component"]).strip()
        if not original:
            continue

        target = PSEUDO_TO_AGA8_HEAVY.get(original, original)

        if target not in _AGA8_COMPONENTS_SET:
            if original not in removed:
                removed.append(original)
            continue

        if target != original and (original, target) not in seen_assignments:
            assignments.append((original, target))
            seen_assignments.add((original, target))

        existing = rows.get(target)
        mol = float(row["MolePercent"]) if pd.notna(row["MolePercent"]) else 0.0

        if existing is None:
            mw = float(row["MW"]) if "MW" in df.columns and pd.notna(row.get("MW")) else float("nan")
            dens = float(row["Dens"]) if "Dens" in df.columns and pd.notna(row.get("Dens")) else float("nan")
            rows[target] = {"MolePercent": mol, "MW": mw, "Dens": dens}
        else:
            existing["MolePercent"] += mol

    converted_df = pd.DataFrame(
        [
            {"Component": component, "MolePercent": payload["MolePercent"], "MW": payload["MW"], "Dens": payload["Dens"]}
            for component, payload in rows.items()
        ],
        columns=list(CANONICAL_COLUMNS),
    )

    canonical_csv_out = export_canonical_composition_csv(converted_df, heavy_component_names="defined")
    return Aga8ConversionResult(
        canonical_csv=canonical_csv_out,
        assignments=tuple(assignments),
        removed=tuple(removed),
    )


def format_aga8_conversion_warning(result: Aga8ConversionResult) -> str | None:
    if not result.assignments and not result.removed:
        return None

    parts: list[str] = ["This saved fluid was converted to the AGA8 composition format."]
    if result.assignments:
        listed = ", ".join(f"{src} -> {dst}" for src, dst in result.assignments)
        parts.append(f"Assigned pseudo-components: {listed}.")
    if result.removed:
        listed = ", ".join(result.removed)
        parts.append(f"Removed unsupported components: {listed}.")
    parts.append("The imported AGA8 composition is therefore not identical to the original saved fluid.")
    return " ".join(parts)


def _disambiguate_name(base_name: str, existing_names: set[str]) -> str:
    if base_name not in existing_names:
        return base_name
    counter = 2
    while True:
        candidate = f"{base_name} ({counter})"
        if candidate not in existing_names:
            return candidate
        counter += 1
