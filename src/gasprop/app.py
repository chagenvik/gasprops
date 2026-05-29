from __future__ import annotations

from pathlib import Path

import streamlit as st

from .composition_input import composition_input, composition_io_controls
from .views import comparison, flash, mix, multi, phase, single, surface, tables, uncertainty, validation

LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logo.png"


VIEW_MAP = {
    "Single Calculation": single.render,
    "Multi-Point Calculation": multi.render,
    "Mix": mix.render,
    "Property Tables": tables.render,
    "3D plot": surface.render,
    "Uncertainty Analysis": uncertainty.render,
    "AGA8 EoS Comparison": comparison.render,
    "AGA8 Validation": validation.render,
    "Flash Calculation": flash.render,
    "Phase Envelope": phase.render,
}


def _render_terms_notice() -> None:
    """Render a non-blocking terms notice with links."""
    st.caption(
        "By using this app, you acknowledge and accept the "
        "[Terms of Use](https://github.com/chagenvik/gasprops/blob/main/TERMS_OF_USE.md) "
        "and [License](https://github.com/chagenvik/gasprops/blob/main/LICENSE)."
    )


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

        /* Highlight NeqSim-backed tabs (Flash + Phase Envelope) */
        [data-testid="stTabs"] [data-baseweb="tab"]:nth-child(9),
        [data-testid="stTabs"] [data-baseweb="tab"]:nth-child(10) {
            border-color: rgba(15, 126, 140, 0.3);
            background: rgba(234, 249, 250, 0.95);
            color: #0f6773;
        }
        [data-testid="stTabs"] [data-baseweb="tab"]:nth-child(9)[aria-selected="true"],
        [data-testid="stTabs"] [data-baseweb="tab"]:nth-child(10)[aria-selected="true"] {
            background: linear-gradient(120deg, #0f8bd5 0%, #14a99a 100%);
            color: white;
            border-color: rgba(13, 122, 133, 0.5);
            box-shadow: 0 8px 18px rgba(16, 132, 143, 0.25);
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
        "Calculates gas properties with **AGA8 DETAIL / GERG-2008** as the primary basis for most workflows. "
        "AGA8 calculations are valid for **single-phase gas** and use the **21-component AGA8 set**."
    )
    st.markdown(
        "The **Flash Calculation** and **Phase Envelope** tabs are using **NeqSim**, which supports multiple phases through various EoS. "
        "These tabs are visually highlighted to distinguish them from the AGA8-based tabs."
    )
    st.markdown(
        "Developed by **Equinor K-lab**, by Christian Hågenvik. This application is built on open-source libraries: "
        "[pvtlib](https://github.com/equinor/pvtlib), "
        "[uncertaintylib](https://github.com/equinor/uncertaintylib), and "
        "[neqsim-python](https://github.com/equinor/neqsim-python)."
    )
    st.caption(
        "The AGA8 DETAIL and GERG-2008 implementations used through pvtlib are based on the official "
        "[NIST AGA8 reference repository](https://github.com/usnistgov/AGA8), via the Rust "
        "[aga8 crate](https://crates.io/crates/aga8)."
    )

    _render_terms_notice()

    st.info(
        "**Calculation scope:** Blue tabs use AGA8 DETAIL/GERG and are valid for single-phase gas within the AGA8 component set. "
        "Teal-highlighted tabs on the right (**Flash Calculation** and **Phase Envelope**) use NeqSim workflows for phase-behavior analysis.",
        icon="ℹ️",
    )

    with st.expander("📖 User guide", expanded=False):
        st.markdown(
            """
Computes thermodynamic and transport properties using two calculation engines:

- **AGA8 DETAIL / GERG-2008** for most property workflows (single-phase gas scope)
- **NeqSim** for phase-behavior workflows (Flash Calculation and Phase Envelope)

**How to use**
1. Enter the gas composition in the table to the right (units: mol%).
2. Use the controls in the left panel to **Set to zero**, **Normalize**, or import via **CSV**.
   You can also load a previously saved session fluid via *Use saved fluid (session)*.
3. Pick a tab:
   - **Single Calculation** — properties at one P, T.
   - **Multi-Point Calculation** — properties at multiple pressure/temperature points.
   - **Mix** — blend two AGA8 fluids by mass, mole, volume, or standard volume.
   - **Property Tables** — sweep over P/T grids; export to CSV/PDF.
   - **3D plot** — visualise a property over a P/T plane.
   - **Uncertainty Analysis** — propagate composition and P/T uncertainty.
   - **AGA8 EoS Comparison** — compare AGA8 calculation modes.
   - **AGA8 Validation** — check composition according to quality ranges in the AGA8 report.
   - **Flash Calculation** — NeqSim TP flash for single tables or P/T ranges, with gas/liquid outputs.
   - **Phase Envelope** — phase-boundary analysis with NeqSim.
4. The composition you enter is shared across all tabs.

**Composition format (AGA8)**
This app accepts only the **21-component AGA8 set**: standard natural-gas components plus H₂O, He, H₂, Ar, CO, O₂, H₂S.
Heavy fractions are the defined normal-alkanes nC6–nC10 (no pseudo C6+ components).

**Saved fluids**
Use *💾 Temporary save fluid* to keep a composition in memory for the current browser session,
and *Use saved fluid (session)* to reload it later. The library is cleared on tab close, refresh,
or app restart, with a cap of 20 fluids per session. The **Mix** tab can use current composition,
example gases, and session-saved AGA8 fluids.

**Things to be aware of**
- AGA8 properties assume **single-phase gas**. Always sanity-check your point against the phase envelope before reading out densities/viscosities.
- For calculations in the **two-phase region**, use the **Flash Calculation** tab.
- The DETAIL method is restricted to a smaller component set than GERG-2008; GERG-2008 covers a wider range of compositions, pressure, and temperature, and is normally the safer choice for natural gas mixtures.
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
        "**Legal Notice (Warranty Disclaimer and Limitation of Liability):** This software is provided **as-is**, "
        "without warranty of any kind, express or implied, "
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
        "**Terms of Use:** [See TERMS_OF_USE on GitHub](https://github.com/chagenvik/gasprops/blob/main/TERMS_OF_USE.md)."
    )
    st.markdown(
        "**License:** MIT - [See LICENSE on GitHub](https://github.com/chagenvik/gasprops/blob/main/LICENSE)."
    )
