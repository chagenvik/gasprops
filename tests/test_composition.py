from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gasprop.composition import composition_from_csv_text, composition_from_dict, load_example_composition


class CompositionTests(unittest.TestCase):
    def test_example_round_trip(self):
        comp = load_example_composition("lean_gas")
        frame = composition_from_dict(comp)
        round_tripped = composition_from_csv_text(frame.to_csv(index=False))
        self.assertAlmostEqual(sum(round_tripped.values()), 100.0, places=4)
        self.assertAlmostEqual(round_tripped["C1"], comp["C1"], places=4)

    def test_csv_import(self):
        text = "Component,MolePercent\nC1,95\nCO2,5\n"
        comp = composition_from_csv_text(text)
        self.assertAlmostEqual(comp["C1"], 95.0, places=4)
        self.assertAlmostEqual(comp["CO2"], 5.0, places=4)


if __name__ == "__main__":
    unittest.main()
