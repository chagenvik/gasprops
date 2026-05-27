from __future__ import annotations

from pathlib import Path

import streamlit as st

from .composition_input import composition_input, composition_io_controls
from .views import comparison, flash, mix, multi, phase, single, surface, tables, uncertainty, validation

LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logo.png"


VIEW_MAP = {
    "Single Calculation": single.render,
    "Multi-Point Calculation": multi.render,
    "Flash Calculation": flash.render,
    "Mix": mix.render,
    "Property Tables": tables.render,
    "3D plot": surface.render,
    "Phase Envelope": phase.render,
    "Uncertainty Analysis": uncertainty.render,
    "AGA8 EoS Comparison": comparison.render,
    "AGA8 Validation": validation.render,
}


def _require_legal_acknowledgement() -> None:
    """Require user acknowledgement of use-at-own-risk terms once per browser session."""
    accepted_key = "legal_acknowledged_session"
    if accepted_key not in st.session_state:
        st.session_state[accepted_key] = False

    if st.session_state[accepted_key]:
        return

    st.warning(
        "**Use at your own risk.** This app is provided as-is without warranty and is for informational use only. "
        "It is not a certified engineering or operational decision tool. You are responsible for independent verification "
        "before any safety-critical, operational, financial, or regulatory use.",
        icon="⚠️",
    )
    accepted = st.checkbox(
        "I understand and accept these terms for this browser session.",
        key="legal_accept_checkbox",
    )
    st.caption("License: MIT. See full text in the repository LICENSE.")

    if accepted:
        st.session_state[accepted_key] = True
        st.rerun()

    st.stop()


def run_app() -> None:
    """Render the main GasProps app layout and tabs."""
    st.set_page_config(page_title="GasProps", page_icon="🧪", layout="wide")
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 10% 5%, rgba(173, 216, 255, 0.45) 0%, rgba(173, 216, 255, 0) 35%),
                radial-gradient(circle at 90% 95%, rgba(122, 194, 255, 0.35) 0%, rgba(122, 194, 255, 0) 40%),
                linear-gradient(145deg, #eef8ff 0%, #dff1ff 38%, #d2ebff 68%, #eaf7ff 100%);
            background-size: 120% 120%;
            animation: bg-shift 18s ease-in-out infinite;
        }
        [data-testid="stHeader"] {
            background: transparent;
        }
        .block-container {
            max-width: 1300px;
            padding-left: 3rem;
            padding-right: 3rem;
            padding-top: 1.4rem;
            padding-bottom: 2.2rem;
            background: rgba(255, 255, 255, 0.76);
            border: 1px solid rgba(255, 255, 255, 0.85);
            border-radius: 24px;
            box-shadow: 0 18px 40px rgba(22, 90, 140, 0.16);
            backdrop-filter: blur(6px);
        }

        h1, h2, h3, h4 {
            color: #083a5f;
            letter-spacing: 0.01em;
        }
        p, li {
            color: #194f73;
        }

        [data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 0.4rem;
        }
        [data-testid="stTabs"] [data-baseweb="tab"] {
            border-radius: 999px;
            border: 1px solid rgba(8, 88, 140, 0.16);
            background: rgba(255, 255, 255, 0.85);
            color: #19567d;
            padding: 0.38rem 0.95rem;
            transition: all 0.2s ease;
        }
        [data-testid="stTabs"] [aria-selected="true"] {
            background: linear-gradient(120deg, #0f8bd5 0%, #35b7ff 100%);
            color: white;
            border-color: rgba(8, 114, 180, 0.45);
            box-shadow: 0 8px 18px rgba(27, 125, 183, 0.25);
        }

        .stButton > button {
            border: 0;
            border-radius: 12px;
            background: linear-gradient(120deg, #0f8bd5 0%, #2fb7ff 100%);
            color: white;
            box-shadow: 0 8px 18px rgba(18, 126, 191, 0.24);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 12px 22px rgba(18, 126, 191, 0.28);
        }

        [data-testid="stAlert"] {
            border-radius: 14px;
            border: 1px solid rgba(20, 105, 155, 0.2);
            background: rgba(255, 255, 255, 0.78);
            box-shadow: 0 8px 18px rgba(19, 103, 154, 0.12);
        }

        @keyframes bg-shift {
            0% { background-position: 0% 0%; }
            50% { background-position: 100% 100%; }
            100% { background-position: 0% 0%; }
        }

        @media (max-width: 900px) {
            .block-container {
                border-radius: 16px;
                padding-left: 1rem;
                padding-right: 1rem;
            }
            [data-testid="stTabs"] [data-baseweb="tab"] {
                padding: 0.35rem 0.7rem;
                font-size: 0.86rem;
            }
        }

        @media (prefers-reduced-motion: reduce) {
            [data-testid="stAppViewContainer"] {
                animation: none;
            }
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
        "multi-point tables, flash calculations, fluid mixing, 3D surface plots, and phase envelope calculations via SRK/neqsim."
    )
    st.markdown(
        "Developed by **Equinor K-lab**, by Christian Hågenvik. This application is built on open-source libraries: "
        "[pvtlib](https://github.com/equinor/pvtlib), "
        "[uncertaintylib](https://github.com/equinor/uncertaintylib), and "
        "[neqsim-python](https://github.com/equinor/neqsim-python)."
    )

    _require_legal_acknowledgement()

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
                    - **Flash Calculation** — NeqSim TP flash for single tables or P/T ranges, with gas/liquid outputs.
                    - **Mix** — blend two AGA8 fluids by mass, mole, volume, or standard volume.
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
            The **Mix** tab can use current composition, example gases, and session-saved AGA8 fluids.

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
        "**Disclaimer:** This software is provided **as-is**, without warranty of any kind, express or implied, "
        "including merchantability, fitness for a particular purpose, non-infringement, accuracy, or completeness. "
        "The app is for informational and educational use only and is not a certified engineering, safety, or "
        "operational decision tool. Results may be inaccurate, incomplete, or unsuitable for a specific use case. "
        "Users are solely responsible for interpretation, validation, and use of outputs, and for compliance with "
        "applicable laws, regulations, standards, and internal procedures. Independent verification by qualified "
        "professionals is required before any design, operational, safety-critical, financial, or regulatory decision. "
        "To the maximum extent permitted by law, the authors, contributors, and distributors are not liable for any "
        "direct, indirect, incidental, special, exemplary, consequential, or other damages (including data loss, "
        "profit loss, production loss, or business interruption) arising from use of, or inability to use, this "
        "software, even if advised of the possibility of such damages. Use of this app constitutes acceptance of "
        "these terms."
    )
    st.markdown(
        "**License:** MIT - [See LICENSE on GitHub](https://github.com/chagenvik/gasprops/blob/main/LICENSE)."
    )
