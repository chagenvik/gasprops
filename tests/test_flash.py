import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gasprop.views import flash


def test_kinematic_viscosity_is_default_flash_output_property():
    assert "kinematic_viscosity" in flash.DEFAULT_PROPERTIES
