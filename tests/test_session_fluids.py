from pathlib import Path
import sys

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from utils.session_fluids import (
    FORMAT_AGA8,
    SESSION_FLUIDS_KEY,
    clear_session_fluids,
    list_session_fluids,
    save_session_fluid,
)


def test_save_session_fluid_is_listed_immediately_and_replaces_registry():
    st.session_state[SESSION_FLUIDS_KEY] = []
    original_registry = st.session_state[SESSION_FLUIDS_KEY]

    try:
        fluid = save_session_fluid(
            canonical_csv="Component,MolePercent\nC1,100\n",
            format_family=FORMAT_AGA8,
            source_module="test",
            base_name="Saved test gas",
        )

        saved_fluids = list_session_fluids(format_family=FORMAT_AGA8)

        assert len(saved_fluids) == 1
        assert saved_fluids[0].id == fluid.id
        assert saved_fluids[0].display_name == "Saved test gas"
        assert st.session_state[SESSION_FLUIDS_KEY] is not original_registry
    finally:
        clear_session_fluids()