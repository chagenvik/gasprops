from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import numpy as np
import pvtlib

from .domain import COMPONENTS

MixBasis = Literal["mass", "mole", "volume", "std_volume"]

_COMPONENT_NAMES: tuple[str, ...] = tuple(COMPONENTS.keys())
_COMPONENT_MW = np.array([COMPONENTS[name].mw_g_mol for name in _COMPONENT_NAMES], dtype=float)


@dataclass(frozen=True)
class MixResult:
    fluid1_name: str
    fluid2_name: str
    basis: MixBasis
    ratio_fluid1: float
    amount1: float
    amount2: float
    mass1_kg: float
    mass2_kg: float
    total_mass_kg: float
    moles1_kmol: float
    moles2_kmol: float
    total_moles_kmol: float
    mw1_kg_per_kmol: float
    mw2_kg_per_kmol: float
    mixed_mw_kg_per_kmol: float
    density1_used_kg_m3: float | None
    density2_used_kg_m3: float | None
    combined_density_kg_m3: float | None
    composition_mol_percent: dict[str, float]
    label: str


@lru_cache(maxsize=1)
def _aga8() -> pvtlib.AGA8:
    return pvtlib.AGA8("GERG-2008")


def _normalized_vector(values: dict[str, float]) -> np.ndarray:
    vec = np.array([float(values.get(name, 0.0)) for name in _COMPONENT_NAMES], dtype=float)
    vec = np.where(vec > 0.0, vec, 0.0)
    total = float(vec.sum())
    if total <= 0.0:
        raise ValueError("Composition total must be greater than zero.")
    return vec / total


def _mw_from_x(mole_fractions: np.ndarray) -> float:
    return float(np.dot(mole_fractions, _COMPONENT_MW))


def _density_from_x(mole_fractions: np.ndarray, p_barg: float, t_c: float) -> float:
    composition = {
        name: float(x * 100.0)
        for name, x in zip(_COMPONENT_NAMES, mole_fractions)
        if x > 0.0
    }
    result = _aga8().calculate_from_PT(
        composition=composition,
        pressure=float(p_barg) + 1.01325,
        temperature=float(t_c) + 273.15,
        pressure_unit="bara",
        temperature_unit="K",
    )
    return float(result["rho"])


def _basis_label(basis: MixBasis) -> str:
    return {
        "mass": "mass",
        "mole": "mole",
        "volume": "vol",
        "std_volume": "Sm3",
    }[basis]


def _moles_from_basis(
    basis: MixBasis,
    amount1: float,
    amount2: float,
    mw1: float,
    mw2: float,
    x1: np.ndarray,
    x2: np.ndarray,
    p_barg: float | None,
    t_c: float | None,
) -> tuple[float, float, float | None, float | None, float | None]:
    rho1: float | None = None
    rho2: float | None = None
    combined_density: float | None = None

    if basis == "mass":
        mass1 = float(amount1)
        mass2 = float(amount2)
        n1 = mass1 / mw1 if mw1 > 0.0 else 0.0
        n2 = mass2 / mw2 if mw2 > 0.0 else 0.0
    elif basis == "mole":
        n1 = float(amount1)
        n2 = float(amount2)
        mass1 = n1 * mw1
        mass2 = n2 * mw2
    elif basis == "volume":
        if p_barg is None or t_c is None:
            raise ValueError("P [barg] and T [C] are required for volume-based mixing.")
        rho1 = _density_from_x(x1, p_barg, t_c)
        rho2 = _density_from_x(x2, p_barg, t_c)
        mass1 = float(amount1) * rho1
        mass2 = float(amount2) * rho2
        n1 = mass1 / mw1 if mw1 > 0.0 else 0.0
        n2 = mass2 / mw2 if mw2 > 0.0 else 0.0
        total_vol = float(amount1) + float(amount2)
        if total_vol > 0.0:
            combined_density = (mass1 + mass2) / total_vol
    elif basis == "std_volume":
        rho1 = _density_from_x(x1, 0.0, 15.0)
        rho2 = _density_from_x(x2, 0.0, 15.0)
        mass1 = float(amount1) * rho1
        mass2 = float(amount2) * rho2
        n1 = mass1 / mw1 if mw1 > 0.0 else 0.0
        n2 = mass2 / mw2 if mw2 > 0.0 else 0.0
        total_vol = float(amount1) + float(amount2)
        if total_vol > 0.0:
            combined_density = (mass1 + mass2) / total_vol
    else:
        raise ValueError(f"Unsupported mixing basis: {basis!r}")

    total_mass = mass1 + mass2
    if total_mass <= 0.0:
        raise ValueError("Total mass is zero - cannot mix fluids with zero amounts.")

    return n1, n2, rho1, rho2, combined_density


def mix_two(
    comp1: dict[str, float],
    comp2: dict[str, float],
    *,
    fluid1_name: str,
    fluid2_name: str,
    basis: MixBasis,
    amount1: float,
    amount2: float,
    p_barg: float | None = None,
    t_c: float | None = None,
) -> MixResult:
    x1 = _normalized_vector(comp1)
    x2 = _normalized_vector(comp2)

    mw1 = _mw_from_x(x1)
    mw2 = _mw_from_x(x2)

    n1, n2, rho1, rho2, combined_density = _moles_from_basis(
        basis,
        amount1,
        amount2,
        mw1,
        mw2,
        x1,
        x2,
        p_barg,
        t_c,
    )

    total_moles = n1 + n2
    if total_moles <= 0.0:
        raise ValueError("Total moles are zero - cannot build mixed composition.")

    moles_by_component = (x1 * n1) + (x2 * n2)
    mixed_x = moles_by_component / float(moles_by_component.sum())
    mixed_mw = _mw_from_x(mixed_x)

    mass1 = n1 * mw1
    mass2 = n2 * mw2
    total_mass = mass1 + mass2
    ratio1 = mass1 / total_mass

    pct1 = int(round(ratio1 * 100.0))
    pct2 = 100 - pct1
    label = f"Mix: {fluid1_name} + {fluid2_name} ({pct1}:{pct2} {_basis_label(basis)})"

    composition_percent = {
        name: float(x * 100.0)
        for name, x in zip(_COMPONENT_NAMES, mixed_x)
        if x > 0.0
    }

    return MixResult(
        fluid1_name=fluid1_name,
        fluid2_name=fluid2_name,
        basis=basis,
        ratio_fluid1=ratio1,
        amount1=float(amount1),
        amount2=float(amount2),
        mass1_kg=mass1,
        mass2_kg=mass2,
        total_mass_kg=total_mass,
        moles1_kmol=n1,
        moles2_kmol=n2,
        total_moles_kmol=total_moles,
        mw1_kg_per_kmol=mw1,
        mw2_kg_per_kmol=mw2,
        mixed_mw_kg_per_kmol=mixed_mw,
        density1_used_kg_m3=rho1,
        density2_used_kg_m3=rho2,
        combined_density_kg_m3=combined_density,
        composition_mol_percent=composition_percent,
        label=label,
    )


def mix_range(
    comp1: dict[str, float],
    comp2: dict[str, float],
    *,
    fluid1_name: str,
    fluid2_name: str,
    basis: MixBasis,
    ratios_percent: list[float],
    total_amount: float = 100.0,
    p_barg: float | None = None,
    t_c: float | None = None,
) -> list[MixResult]:
    if not ratios_percent:
        raise ValueError("ratios_percent must not be empty.")

    x1 = _normalized_vector(comp1)
    x2 = _normalized_vector(comp2)
    mw1 = _mw_from_x(x1)
    mw2 = _mw_from_x(x2)

    ratios = np.asarray(ratios_percent, dtype=float)
    if np.any((ratios < 0.0) | (ratios > 100.0)):
        raise ValueError("All ratios must be within [0, 100].")

    fractions = ratios / 100.0

    rho1: float | None = None
    rho2: float | None = None
    if basis == "mass":
        mass1 = fractions * float(total_amount)
        mass2 = (1.0 - fractions) * float(total_amount)
        n1 = mass1 / mw1
        n2 = mass2 / mw2
        combined_density = np.full_like(fractions, np.nan, dtype=float)
    elif basis == "mole":
        n1 = fractions * float(total_amount)
        n2 = (1.0 - fractions) * float(total_amount)
        mass1 = n1 * mw1
        mass2 = n2 * mw2
        combined_density = np.full_like(fractions, np.nan, dtype=float)
    elif basis == "volume":
        if p_barg is None or t_c is None:
            raise ValueError("P [barg] and T [C] are required for volume-based mixing.")
        rho1 = _density_from_x(x1, p_barg, t_c)
        rho2 = _density_from_x(x2, p_barg, t_c)
        vol1 = fractions * float(total_amount)
        vol2 = (1.0 - fractions) * float(total_amount)
        mass1 = vol1 * rho1
        mass2 = vol2 * rho2
        n1 = mass1 / mw1
        n2 = mass2 / mw2
        total_vol = vol1 + vol2
        combined_density = np.where(total_vol > 0.0, (mass1 + mass2) / total_vol, np.nan)
    elif basis == "std_volume":
        rho1 = _density_from_x(x1, 0.0, 15.0)
        rho2 = _density_from_x(x2, 0.0, 15.0)
        vol1 = fractions * float(total_amount)
        vol2 = (1.0 - fractions) * float(total_amount)
        mass1 = vol1 * rho1
        mass2 = vol2 * rho2
        n1 = mass1 / mw1
        n2 = mass2 / mw2
        total_vol = vol1 + vol2
        combined_density = np.where(total_vol > 0.0, (mass1 + mass2) / total_vol, np.nan)
    else:
        raise ValueError(f"Unsupported mixing basis: {basis!r}")

    total_mass = mass1 + mass2
    if np.any(total_mass <= 0.0):
        raise ValueError("Total mass is zero for at least one ratio.")

    total_moles = n1 + n2
    if np.any(total_moles <= 0.0):
        raise ValueError("Total moles are zero for at least one ratio.")

    moles_matrix = (n1[:, None] * x1[None, :]) + (n2[:, None] * x2[None, :])
    mole_sums = moles_matrix.sum(axis=1)[:, None]
    mixed_x_matrix = moles_matrix / mole_sums
    mixed_mw = mixed_x_matrix @ _COMPONENT_MW

    results: list[MixResult] = []
    for idx in range(len(ratios)):
        ratio1_mass = float(mass1[idx] / total_mass[idx])
        pct1 = int(round(ratio1_mass * 100.0))
        pct2 = 100 - pct1
        label = f"Mix: {fluid1_name} + {fluid2_name} ({pct1}:{pct2} {_basis_label(basis)})"

        composition_percent = {
            name: float(value * 100.0)
            for name, value in zip(_COMPONENT_NAMES, mixed_x_matrix[idx])
            if value > 0.0
        }

        results.append(
            MixResult(
                fluid1_name=fluid1_name,
                fluid2_name=fluid2_name,
                basis=basis,
                ratio_fluid1=ratio1_mass,
                amount1=float(fractions[idx] * total_amount),
                amount2=float((1.0 - fractions[idx]) * total_amount),
                mass1_kg=float(mass1[idx]),
                mass2_kg=float(mass2[idx]),
                total_mass_kg=float(total_mass[idx]),
                moles1_kmol=float(n1[idx]),
                moles2_kmol=float(n2[idx]),
                total_moles_kmol=float(total_moles[idx]),
                mw1_kg_per_kmol=mw1,
                mw2_kg_per_kmol=mw2,
                mixed_mw_kg_per_kmol=float(mixed_mw[idx]),
                density1_used_kg_m3=rho1,
                density2_used_kg_m3=rho2,
                combined_density_kg_m3=float(combined_density[idx]) if not np.isnan(combined_density[idx]) else None,
                composition_mol_percent=composition_percent,
                label=label,
            )
        )

    return results
