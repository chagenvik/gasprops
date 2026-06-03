from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gasprop.composition import composition_from_csv_text, composition_from_dict, load_example_composition
from gasprop.composition_input import distribute_c6_plus


def test_example_round_trip():
    comp = load_example_composition("lean_gas")
    frame = composition_from_dict(comp)
    round_tripped = composition_from_csv_text(frame.to_csv(index=False))
    assert round(sum(round_tripped.values()), 4) == 100.0
    assert round(round_tripped["C1"], 4) == round(comp["C1"], 4)


def test_csv_import():
    text = "Component,MolePercent\nC1,95\nCO2,5\n"
    comp = composition_from_csv_text(text)
    assert round(comp["C1"], 4) == 95.0
    assert round(comp["CO2"], 4) == 5.0


def test_air_example_supported_components_are_normalized():
    comp = load_example_composition("air")

    assert sum(comp.values()) == pytest.approx(100.0, abs=1e-6)
    assert comp["N2"] == pytest.approx(78.079023, abs=1e-6)
    assert comp["O2"] == pytest.approx(20.946265, abs=1e-6)
    assert comp["Ar"] == pytest.approx(0.933940, abs=1e-6)
    assert comp["CO2"] == pytest.approx(0.039997, abs=1e-6)
    assert comp["C1"] == pytest.approx(0.000200, abs=1e-6)
    assert comp["He"] == pytest.approx(0.000524, abs=1e-6)
    assert comp["H2"] == pytest.approx(0.000050, abs=1e-6)
    assert comp["CO"] == pytest.approx(0.0)


def test_distribute_c6_plus_basic():
    """Test nC6 distribution with basic composition."""
    values = {
        "N2": 1.0,
        "CO2": 2.0,
        "C1": 90.3690,
        "C2": 6.0206,
        "C3": 0.5000,
        "iC4": 0.0500,
        "nC4": 0.0500,
        "iC5": 0.0000,
        "nC5": 0.0000,
        "nC6": 0.5,
        "nC7": 0.0,
        "nC8": 0.0,
        "nC9": 0.0,
        "nC10": 0.0,
        "H2O": 0.0,
        "He": 0.0,
        "H2": 0.0,
        "Ar": 0.0,
        "CO": 0.0,
        "O2": 0.0,
        "H2S": 0.0,
    }
    
    result = distribute_c6_plus(values)
    
    # nC6 = 0.5 * 0.50 = 0.25
    assert result["nC6"] == pytest.approx(0.25, abs=1e-6)
    # nC7 = 0.5 * 0.30 = 0.15
    assert result["nC7"] == pytest.approx(0.15, abs=1e-6)
    # nC8 = 0.5 * 0.125 = 0.0625
    assert result["nC8"] == pytest.approx(0.0625, abs=1e-6)
    # nC9 = 0.5 * 0.05 = 0.025
    assert result["nC9"] == pytest.approx(0.025, abs=1e-6)
    # nC10 = 0.5 * 0.025 = 0.0125
    assert result["nC10"] == pytest.approx(0.0125, abs=1e-6)
    
    # Other components should remain unchanged
    assert result["N2"] == pytest.approx(1.0, abs=1e-6)
    assert result["CO2"] == pytest.approx(2.0, abs=1e-6)
    assert result["C1"] == pytest.approx(90.3690, abs=1e-6)


def test_distribute_c6_plus_zero_nc6():
    """Test nC6 distribution when nC6 is zero."""
    values = {
        "N2": 50.0,
        "CO2": 50.0,
        "C1": 0.0,
        "C2": 0.0,
        "C3": 0.0,
        "iC4": 0.0,
        "nC4": 0.0,
        "iC5": 0.0,
        "nC5": 0.0,
        "nC6": 0.0,
        "nC7": 0.0,
        "nC8": 0.0,
        "nC9": 0.0,
        "nC10": 0.0,
        "H2O": 0.0,
        "He": 0.0,
        "H2": 0.0,
        "Ar": 0.0,
        "CO": 0.0,
        "O2": 0.0,
        "H2S": 0.0,
    }
    
    result = distribute_c6_plus(values)
    
    # All C6+ components should be zero
    assert result["nC6"] == pytest.approx(0.0, abs=1e-6)
    assert result["nC7"] == pytest.approx(0.0, abs=1e-6)
    assert result["nC8"] == pytest.approx(0.0, abs=1e-6)
    assert result["nC9"] == pytest.approx(0.0, abs=1e-6)
    assert result["nC10"] == pytest.approx(0.0, abs=1e-6)
    
    # Other components should remain unchanged
    assert result["N2"] == pytest.approx(50.0, abs=1e-6)
    assert result["CO2"] == pytest.approx(50.0, abs=1e-6)
