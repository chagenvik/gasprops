from __future__ import annotations

from pathlib import Path

import streamlit as st

from .composition_input import composition_input, composition_io_controls
from .views import comparison, multi, phase, single, surface, tables, uncertainty, validation

LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logo.png"


VIEW_MAP = {
    "Single Calculation": single.render,
    "Multi-Point Calculation": multi.render,
    "Property Tables": tables.render,
    "3D plot": surface.render,
    "Phase Envelope": phase.render,
    "Uncertainty Analysis": uncertainty.render,
    "AGA8 EoS Comparison": comparison.render,
    "AGA8 Validation": validation.render,
}


def run_app() -> None:
    """Render the main GasProps app layout and tabs."""
    st.set_page_config(page_title="GasProps", page_icon="🧪", layout="wide")
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1300px;
            padding-left: 3rem;
            padding-right: 3rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if LOGO_PATH.exists():
        _, logo_col, _ = st.columns([1, 6, 1])
        with logo_col:
            st.image(str(LOGO_PATH), width=920)
    st.markdown(
        "Calculates thermodynamic and transport properties of natural gas mixtures using the "
        "AGA8 equation of state (GERG-2008 or DETAIL method). Supports single-point calculations, "
        "multi-point tables, 3D surface plots, and phase envelope calculations via SRK/neqsim."
    )
    st.markdown(
        "Developed by **Equinor K-lab**. This application is built on open-source libraries: "
        "[pvtlib](https://github.com/equinor/pvtlib), "
        "[uncertaintylib](https://github.com/equinor/uncertaintylib), and "
        "[neqsim-python](https://github.com/equinor/neqsim-python)."
    )

    st.info(
        "**NOTE:** The AGA8 property calculations are valid for single-phase gas only and do not account for phase boundaries. "
        "Use the **Phase Envelope** tab to check whether your operating conditions fall within the two-phase region "
        "before interpreting the calculated properties.",
        icon="ℹ️",
    )

    with st.expander("📖 User guide", expanded=False):
        st.markdown(
            """
            Computes thermodynamic and transport properties of natural gas mixtures using the
            AGA8 equation of state (GERG-2008 or DETAIL).

            **How to use**
            1. Enter the gas composition in the table to the right (units: mol%).
            2. Use the controls in the left panel to **Set to zero**, **Normalize**, or import
               via **CSV**. You can also load a previously saved session fluid via
               *Use saved fluid (session)* — see "Saved fluids" below.
            3. Pick a tab:
               - **Single Calculation** — properties at one P, T.
               - **Multi-Point Calculation** — properties at multiple pressure/temperature points.
               - **Property Tables** — sweep over P/T grids; export to CSV/PDF.
               - **3D plot** — visualise a property over a P/T plane.
               - **Phase Envelope** — check the phase envelope with NeqSim.
               - **Uncertainty Analysis** — propagate composition and P/T uncertainty.
               - **AGA8 EoS Comparison** — compare AGA8 calculation modes.
               - **AGA8 Validation** — check composition according to quality ranges in the AGA8 report.
            4. The composition you enter is shared across all tabs.

            **Composition format (AGA8)**
            This tool only accepts the **AGA8 component set**: standard natural-gas
            components plus H₂O, He, H₂, Ar, CO, O₂, H₂S. Heavy fractions are the defined
            normal-alkanes nC6–nC10 (no pseudo C6+ components).

            **Saved fluids**
            Use *💾 Temporary save fluid* to keep a composition in memory for the current
            browser session, and *Use saved fluid (session)* to reload it later. The library
            is cleared on tab close, refresh, or app restart, with a cap of 20 fluids per session.

            **Things to be aware of**
            - AGA8 properties assume **single-phase gas**. Always sanity-check your point
              against the phase envelope before reading out densities/viscosities.
            - The DETAIL method is restricted to a smaller component set than GERG-2008;
              choose GERG-2008 if you have non-standard components such as H₂ or He.
            """
        )

    col_ctrl, col_table = st.columns([2, 3], gap="large")
    with col_ctrl:
        st.markdown("#### Gas Composition")
        composition_io_controls(key_prefix="shared")
    with col_table:
        composition = composition_input(key_prefix="shared")

    st.divider()

    tab_labels = list(VIEW_MAP.keys())
    tabs = st.tabs(tab_labels)
    for tab, label in zip(tabs, tab_labels):
        with tab:
            VIEW_MAP[label](composition)

    st.divider()
    st.info(
        "**Disclaimer:** Results are for informational and engineering screening purposes only. "
        "They must be independently verified before any operational, safety-critical, or compliance use. "
        "The tool is provided **as-is**, with no warranty, and the creator is not responsible for "
        "errors, omissions, or decisions made from its outputs.\n\n"
        "**License:** MIT — see `LICENSE`."
    )
