"""Streamlit UI helpers for the per-session fluid library."""

from __future__ import annotations

from typing import Callable

import streamlit as st

from utils.session_fluids import (
    FORMAT_PVTCALC,
    MAX_SESSION_FLUIDS,
    SessionFluid,
    SessionFluidLimitError,
    list_session_fluids,
    save_session_fluid,
)

LIFECYCLE_HELP = (
    "Saved only in memory for this browser session. "
    "Lost when the tab is closed, refreshed, or the app restarts."
)


def render_temporary_save_button(
    *,
    key: str,
    canonical_csv_provider: Callable[[], str],
    format_family: str,
    source_module: str,
    base_name_provider: Callable[[], str],
    source_context: str = "",
    label: str = "💾 Temporary save fluid",
    help_text: str | None = None,
    disabled: bool = False,
) -> SessionFluid | None:
    cap_reached = len(list_session_fluids()) >= MAX_SESSION_FLUIDS
    button_disabled = disabled or cap_reached
    tooltip = help_text or LIFECYCLE_HELP
    if cap_reached:
        tooltip = (
            f"Session fluid library is full ({MAX_SESSION_FLUIDS}). "
            "Delete an existing saved fluid before saving a new one."
        )

    if not st.button(label, key=key, help=tooltip, disabled=button_disabled):
        return None

    try:
        canonical_csv = canonical_csv_provider()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not save fluid: {exc}")
        return None

    if not canonical_csv or not canonical_csv.strip():
        st.warning("Nothing to save: the composition is empty.")
        return None

    try:
        fluid = save_session_fluid(
            canonical_csv=canonical_csv,
            format_family=format_family,
            source_module=source_module,
            base_name=base_name_provider() or "Saved fluid",
            source_context=source_context,
        )
    except SessionFluidLimitError as exc:
        st.error(str(exc))
        return None
    except ValueError as exc:
        st.error(str(exc))
        return None

    st.success(f"Saved as “{fluid.display_name}”. {LIFECYCLE_HELP}")
    return fluid


def render_load_saved_fluid_selector(
    *,
    key: str,
    format_family: str = FORMAT_PVTCALC,
    label: str = "Use saved fluid (session)",
    help_text: str | None = None,
) -> SessionFluid | None:
    fluids = list_session_fluids(format_family=format_family)
    if not fluids:
        return None

    options = {f"{fluid.display_name}": fluid for fluid in fluids}
    options_with_blank = {"— Select saved fluid —": None, **options}

    cols = st.columns([3, 1])
    with cols[0]:
        chosen_label = st.selectbox(
            label,
            list(options_with_blank.keys()),
            key=f"{key}_select",
            help=help_text or LIFECYCLE_HELP,
        )
    with cols[1]:
        load_clicked = st.button(
            "Load",
            key=f"{key}_load",
            disabled=options_with_blank[chosen_label] is None,
        )

    if not load_clicked:
        return None

    return options_with_blank[chosen_label]
