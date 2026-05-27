from pathlib import Path
import sys
 
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import gasprop.mix_logic as mix_logic


FLUID_A = {
    "N2": 1.0,
    "CO2": 2.0,
    "C1": 90.0,
    "C2": 4.0,
    "C3": 2.0,
    "iC4": 0.5,
    "nC4": 0.5,
}

FLUID_B = {
    "H2": 30.0,
    "N2": 2.0,
    "CO2": 3.0,
    "C1": 50.0,
    "C2": 10.0,
    "C3": 3.0,
    "iC4": 1.0,
    "nC4": 1.0,
}


def test_mole_basis_half_half():
    comp1 = {"C1": 100.0}
    comp2 = {"CO2": 100.0}

    result = mix_logic.mix_two(
        comp1,
        comp2,
        fluid1_name="A",
        fluid2_name="B",
        basis="mole",
        amount1=1.0,
        amount2=1.0,
    )

    assert result.composition_mol_percent["C1"] == pytest.approx(50.0, abs=1e-6)
    assert result.composition_mol_percent["CO2"] == pytest.approx(50.0, abs=1e-6)


def test_mass_basis_respects_molecular_weight():
    comp1 = {"C1": 100.0}
    comp2 = {"CO2": 100.0}

    result = mix_logic.mix_two(
        comp1,
        comp2,
        fluid1_name="A",
        fluid2_name="B",
        basis="mass",
        amount1=1.0,
        amount2=1.0,
    )

    assert result.composition_mol_percent["C1"] > result.composition_mol_percent["CO2"]


def test_range_mixing_vectorized_outputs():
    comp1 = {"C1": 100.0}
    comp2 = {"CO2": 100.0}
    ratios = [0.0, 25.0, 50.0, 75.0, 100.0]

    results = mix_logic.mix_range(
        comp1,
        comp2,
        fluid1_name="A",
        fluid2_name="B",
        basis="mole",
        ratios_percent=ratios,
        total_amount=100.0,
    )

    assert len(results) == len(ratios)
    assert results[0].composition_mol_percent["CO2"] == pytest.approx(100.0, abs=1e-6)
    assert results[-1].composition_mol_percent["C1"] == pytest.approx(100.0, abs=1e-6)


def test_volume_basis_uses_density_conversion():
    comp1 = {"C1": 100.0}
    comp2 = {"CO2": 100.0}

    original_density = mix_logic._density_from_x
    try:
        mix_logic._density_from_x = lambda x, p, t: 2.0
        result = mix_logic.mix_two(
            comp1,
            comp2,
            fluid1_name="A",
            fluid2_name="B",
            basis="volume",
            amount1=10.0,
            amount2=10.0,
            p_barg=10.0,
            t_c=20.0,
        )
    finally:
        mix_logic._density_from_x = original_density

    assert result.density1_used_kg_m3 is not None
    assert result.density2_used_kg_m3 is not None


def test_fluid_a_fluid_b_mole_50_50_reference_case():
    result = mix_logic.mix_two(
        FLUID_A,
        FLUID_B,
        fluid1_name="Fluid A",
        fluid2_name="Fluid B",
        basis="mole",
        amount1=50.0,
        amount2=50.0,
    )

    expected = {
        "H2": 15.000,
        "N2": 1.500,
        "CO2": 2.500,
        "C1": 70.000,
        "C2": 7.000,
        "C3": 2.500,
        "iC4": 0.750,
        "nC4": 0.750,
    }

    for component, value in expected.items():
        assert result.composition_mol_percent.get(component, 0.0) == pytest.approx(value, abs=1e-3)


def test_fluid_a_fluid_b_mass_50_50_reference_case():
    result = mix_logic.mix_two(
        FLUID_A,
        FLUID_B,
        fluid1_name="Fluid A",
        fluid2_name="Fluid B",
        basis="mass",
        amount1=50.0,
        amount2=50.0,
    )

    expected = {
        "H2": 15.992,
        "N2": 1.533,
        "CO2": 2.533,
        "C1": 68.677,
        "C2": 7.198,
        "C3": 2.533,
        "iC4": 0.767,
        "nC4": 0.767,
    }

    for component, value in expected.items():
        assert result.composition_mol_percent.get(component, 0.0) == pytest.approx(value, abs=1e-3)


def test_fluid_a_fluid_b_mole_30_70_reference_case():
    result = mix_logic.mix_two(
        FLUID_A,
        FLUID_B,
        fluid1_name="Fluid A",
        fluid2_name="Fluid B",
        basis="mole",
        amount1=30.0,
        amount2=70.0,
    )

    expected = {
        "H2": 21.000,
        "N2": 1.700,
        "CO2": 2.700,
        "C1": 62.000,
        "C2": 8.200,
        "C3": 2.700,
        "iC4": 0.850,
        "nC4": 0.850,
    }

    for component, value in expected.items():
        assert result.composition_mol_percent.get(component, 0.0) == pytest.approx(value, abs=1e-3)


def test_pure_methane_hydrogen_mole_50_50():
    result = mix_logic.mix_two(
        {"C1": 100.0},
        {"H2": 100.0},
        fluid1_name="Methane",
        fluid2_name="Hydrogen",
        basis="mole",
        amount1=50.0,
        amount2=50.0,
    )

    assert result.composition_mol_percent.get("C1", 0.0) == pytest.approx(50.0, abs=1e-6)
    assert result.composition_mol_percent.get("H2", 0.0) == pytest.approx(50.0, abs=1e-6)
