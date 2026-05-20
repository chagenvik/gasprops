from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gasprop.validation import validate_composition, validate_state


class ValidationTests(unittest.TestCase):
    def test_validation_detects_out_of_range(self):
        comp = {"C1": 40.0, "CO2": 40.0, "N2": 20.0}
        issues = validate_composition(comp, mode="DETAIL")
        self.assertTrue(issues)

    def test_state_validation(self):
        issues = validate_state(800.0, 500.0, mode="GERG-2008")
        self.assertTrue(issues)


if __name__ == "__main__":
    unittest.main()
