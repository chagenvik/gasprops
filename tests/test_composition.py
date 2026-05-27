from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gasprop.composition import composition_from_csv_text, composition_from_dict, load_example_composition


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
