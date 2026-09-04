"""Guard the in-app user guide against drifting away from what the GUI actually offers."""

from pathlib import Path
import inspect
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import gasprop.app as app
from utils.session_fluids import MAX_SESSION_FLUIDS


@pytest.fixture
def guide_text() -> str:
    return inspect.getsource(app.run_app)


# ── No positional references ──────────────────────────────────────────────────
@pytest.mark.parametrize(
    "phrase",
    [
        "to the right",
        "to the left",
        "left panel",
        "right panel",
        "tabs on the right",
        "tabs at the end",
        "table above",
    ],
)
def test_guide_avoids_positional_references(guide_text, phrase):
    # Layout wording goes stale whenever a widget or tab moves; describe controls by
    # their label instead of where they happen to sit.
    assert phrase not in guide_text.lower()


# ── Every tab is documented, and nothing extra ────────────────────────────────
def test_every_tab_is_described_in_the_guide(guide_text):
    missing = [label for label in app.VIEW_MAP if f"**{label}**" not in guide_text]
    assert missing == []


# ── Claims that must match the real widgets ───────────────────────────────────
@pytest.mark.parametrize(
    "control",
    [
        "Set to zero",
        "Normalize",
        "Distribute C6+",
        "Import composition (CSV)",
        "Export composition (CSV)",
        "Use example gases",
        "Use saved fluid (session)",
        "Temporary save fluid",
    ],
)
def test_documented_controls_exist_in_the_ui(control):
    sources = [
        Path(app.__file__).parent / "composition_input.py",
        Path(app.__file__).parents[1] / "utils" / "session_fluids_ui.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    assert control in combined


def test_session_fluid_cap_in_the_guide_matches_the_code(guide_text):
    assert f"cap of {MAX_SESSION_FLUIDS} fluids" in guide_text


def test_guide_reports_all_three_flash_phases(guide_text):
    # The Flash tab exposes gas, liquid and aqueous phases.
    from gasprop.views.flash import PHASE_OPTIONS

    assert set(PHASE_OPTIONS) == {"gas", "liquid", "aqueous"}
    assert "gas/liquid/aqueous" in guide_text


def test_guide_mentions_the_pdf_export_that_property_tables_provides(guide_text):
    tables_source = (Path(app.__file__).parent / "views" / "tables.py").read_text(encoding="utf-8")

    assert "PdfPages" in tables_source
    assert "PDF" in guide_text


def test_guide_describes_the_mix_sub_tabs(guide_text):
    mix_source = (Path(app.__file__).parent / "views" / "mix.py").read_text(encoding="utf-8")

    assert '["Single Mix", "Range Mix"]' in mix_source
    assert "single mix or over a mixing-ratio range" in guide_text


def test_guide_describes_the_dp_flow_sub_tabs(guide_text):
    dp_source = (Path(app.__file__).parent / "views" / "dp_flow.py").read_text(encoding="utf-8")

    assert '"Single point", "Multi-point", "Sizing (solve Δp)"' in dp_source
    assert "single-point, multi-point and Δp-sizing" in guide_text


def test_guide_describes_the_eos_comparison_as_detail_vs_gerg(guide_text):
    assert "DETAIL vs GERG-2008" in guide_text
