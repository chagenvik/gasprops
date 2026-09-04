from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from .composition_input import composition_input, composition_io_controls
from .views import (
    aga8_vs_refprop,
    comparison,
    dp_flow,
    flash,
    flow_converter,
    mix,
    multi,
    phase,
    single,
    surface,
    tables,
    uncertainty,
    validation,
)

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
    "AGA8 vs REFPROP": aga8_vs_refprop.render,
    "Flash Calculation": flash.render,
    "Phase Envelope": phase.render,
    "DP Flow Meter": dp_flow.render,
    "Flow Converter": flow_converter.render,
}

#: Tabs backed by NeqSim rather than AGA8; visually highlighted in the tab bar.
NEQSIM_TAB_LABELS = ("Flash Calculation", "Phase Envelope")

#: Tabs presenting a pre-computed data study; visually highlighted in the tab bar.
DATA_STUDY_TAB_LABELS = ("AGA8 vs REFPROP",)

#: Flow-metering tabs; these answer "how much is flowing" rather than "what are the
#: gas properties", so they get their own highlight colour in the tab bar.
METERING_TAB_LABELS = ("DP Flow Meter", "Flow Converter")

#: CSS placeholder token -> the tab group it should be expanded to.
TAB_HIGHLIGHT_GROUPS: dict[str, tuple[str, ...]] = {
    "NEQSIM_TABS": NEQSIM_TAB_LABELS,
    "DATA_STUDY_TABS": DATA_STUDY_TAB_LABELS,
    "METERING_TABS": METERING_TAB_LABELS,
}


def tab_nth_child_selector(labels: tuple[str, ...], suffix: str = "") -> str:
    """Build a CSS selector list targeting the given tabs by their position in VIEW_MAP.

    Streamlit renders tabs in ``VIEW_MAP`` order, so the highlight styling is derived
    from that order instead of hard-coded indices that silently break when a tab is
    added or reordered.
    """
    order = list(VIEW_MAP.keys())
    selectors = [
        f'[data-testid="stTabs"] [data-baseweb="tab"]:nth-child({order.index(label) + 1}){suffix}'
        for label in labels
        if label in order
    ]
    return ",\n        ".join(selectors)


def _apply_tab_highlight_selectors(css: str) -> str:
    """Expand every ``__<GROUP>__`` / ``__<GROUP>_SELECTED__`` token in the stylesheet.

    Raises if a placeholder token survives, so a renamed or misspelled group fails loudly
    instead of leaking a literal ``__FOO__`` into the rendered CSS.
    """
    for token, labels in TAB_HIGHLIGHT_GROUPS.items():
        css = css.replace(
            f"__{token}_SELECTED__", tab_nth_child_selector(labels, '[aria-selected="true"]')
        )
        css = css.replace(f"__{token}__", tab_nth_child_selector(labels))

    leftover = re.findall(r"__[A-Z_]+__", css)
    if leftover:
        raise ValueError(f"Unresolved tab highlight placeholders in stylesheet: {sorted(set(leftover))}")
    return css


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
        _apply_tab_highlight_selectors(
            """
        <style>
        :root {
            /* Prevent Safari from auto-darkening native controls on dark-mode devices. */
            color-scheme: light !important;
        }
        html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"] {
            color-scheme: light !important;
        }

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
            flex-wrap: wrap;
            gap: 0.4rem;
            row-gap: 0.55rem;
            overflow: visible;
            height: auto;
        }
        [data-testid="stTabs"] [data-baseweb="tab"] {
            border-radius: 999px;
            border: 1px solid rgba(8, 88, 140, 0.16);
            background: rgba(255, 255, 255, 0.85);
            color: #19567d;
            padding: 0.38rem 0.95rem;
            flex: 0 0 auto;
            transition: all 0.2s ease;
        }
        [data-testid="stTabs"] [aria-selected="true"] {
            background: linear-gradient(120deg, #0f8bd5 0%, #35b7ff 100%);
            color: white;
            border-color: rgba(8, 114, 180, 0.45);
            box-shadow: 0 8px 18px rgba(27, 125, 183, 0.25);
        }

        /* Highlight NeqSim-backed tabs (Flash + Phase Envelope) */
        __NEQSIM_TABS__ {
            border-color: rgba(15, 126, 140, 0.3);
            background: rgba(234, 249, 250, 0.95);
            color: #0f6773;
        }
        __NEQSIM_TABS_SELECTED__ {
            background: linear-gradient(120deg, #0f8bd5 0%, #14a99a 100%);
            color: white;
            border-color: rgba(13, 122, 133, 0.5);
            box-shadow: 0 8px 18px rgba(16, 132, 143, 0.25);
        }

        /* Distinguish the AGA8 vs REFPROP tab (data-study tab) */
        __DATA_STUDY_TABS__ {
            border-color: rgba(124, 58, 173, 0.32);
            background: rgba(245, 238, 252, 0.95);
            color: #6b2fae;
        }
        __DATA_STUDY_TABS_SELECTED__ {
            background: linear-gradient(120deg, #7c3aad 0%, #a465e6 100%);
            color: white;
            border-color: rgba(108, 47, 174, 0.5);
            box-shadow: 0 8px 18px rgba(108, 47, 174, 0.25);
        }

        /* Distinguish the flow-metering tabs (DP Flow Meter + Flow Conversion) */
        __METERING_TABS__ {
            border-color: rgba(191, 106, 20, 0.32);
            background: rgba(255, 244, 230, 0.95);
            color: #a45a10;
        }
        __METERING_TABS_SELECTED__ {
            background: linear-gradient(120deg, #d97b12 0%, #f5a742 100%);
            color: white;
            border-color: rgba(176, 96, 16, 0.5);
            box-shadow: 0 8px 18px rgba(176, 96, 16, 0.25);
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

        /* iOS/Safari can still dark-style controls in dark appearance; enforce light widget surfaces. */
        @media (prefers-color-scheme: dark) {
            [data-testid="stFileUploaderDropzone"],
            [data-testid="stDataFrame"],
            [data-testid="stExpander"],
            [data-testid="stAlert"],
            [data-testid="stMetric"],
            [data-baseweb="input"] > div,
            [data-baseweb="select"] > div,
            .stNumberInput input,
            .stTextInput input,
            .stTextArea textarea {
                background: rgba(255, 255, 255, 0.92) !important;
                color: #083a5f !important;
                border-color: rgba(8, 88, 140, 0.2) !important;
            }
            [data-testid="stFileUploaderDropzoneInstructions"],
            [data-testid="stFileUploaderFileData"],
            [data-testid="stDataFrame"] *,
            [data-testid="stMarkdownContainer"] *,
            [data-testid="stWidgetLabel"] {
                color: #083a5f !important;
            }
        }
        </style>
        """
        ),
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
        "The **DP Flow Meter** and **Flow Converter** tabs cover flow metering rather than gas properties. "
        "Both groups are colour-coded in the tab bar to distinguish them from the AGA8 property tabs."
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
        "**Calculation scope:** Most tabs use AGA8 DETAIL/GERG and are valid for single-phase gas within the AGA8 component set. "
        "**Flash Calculation** and **Phase Envelope** use NeqSim workflows for phase-behavior analysis, and the "
        "**DP Flow Meter** and **Flow Converter** tabs at the end cover flow metering.",
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
   - **AGA8 vs REFPROP** — browse pre-computed GERG-2008/DETAIL deviations vs a REFPROP reference for anonymized metering-station and K-lab gases, filterable by AGA8 quality range.
   - **DP Flow Meter** — flow rate through Venturi, orifice and V-cone DP meters (ISO 5167) using AGA8 gas properties.
   - **Flow Converter** — convert between mass flow, actual volume flow and standard volume flow at any P/T and time basis.
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
