"""
Composition Quality Validation Component

Validates gas compositions against AGA8 Part 2 standards:
- DETAIL: Pipeline quality natural gas (strict limits)
- GERG-2008: Intermediate quality natural gas (relaxed limits)
"""

import streamlit as st
import pandas as pd

COMPONENTS_METADATA = [
    ("Methane", "C1"),
    ("Nitrogen", "N2"),
    ("Carbon dioxide", "CO2"),
    ("Ethane", "C2"),
    ("Propane", "C3"),
    ("Isobutane+n-Butane", "iC4+nC4"),
    ("Isopentane+n-Pentane", "iC5+nC5"),
    ("n-Hexane", "nC6"),
    ("n-Heptane", "nC7"),
    ("Octane+Nonane+Decane", "nC8+nC9+nC10"),
    ("Hydrogen", "H2"),
    ("Oxygen", "O2"),
    ("Carbon monoxide", "CO"),
    ("Water", "H2O"),
    ("Hydrogen sulfide", "H2S"),
    ("Helium", "He"),
    ("Argon", "Ar"),
]

DETAIL_RANGES = {
    "C1": (0.70, 1.00),
    "N2": (0.00, 0.20),
    "CO2": (0.00, 0.20),
    "C2": (0.00, 0.10),
    "C3": (0.00, 0.035),
    "iC4": (0.00, 0.0075),
    "nC4": (0.00, 0.0075),
    "iC5": (0.00, 0.0025),
    "nC5": (0.00, 0.0025),
    "nC6": (0.00, 0.001),
    "nC7": (0.00, 0.0005),
    "nC8": (0.00, 0.000167),
    "nC9": (0.00, 0.000167),
    "nC10": (0.00, 0.000167),
    "H2": (0.00, 0.10),
    "O2": (0.00, 0.0002),
    "CO": (0.00, 0.03),
    "H2O": (0.00, 0.00015),
    "H2S": (0.00, 0.0002),
    "He": (0.00, 0.005),
    "Ar": (0.00, 0.0002),
}

GERG_RANGES = {
    "C1": (0.30, 1.00),
    "N2": (0.00, 0.55),
    "CO2": (0.00, 0.30),
    "C2": (0.00, 0.25),
    "C3": (0.00, 0.14),
    "iC4": (0.00, 0.03),
    "nC4": (0.00, 0.03),
    "iC5": (0.00, 0.0025),
    "nC5": (0.00, 0.0025),
    "nC6": (0.00, 0.002),
    "nC7": (0.00, 0.001),
    "nC8": (0.00, 0.000167),
    "nC9": (0.00, 0.000167),
    "nC10": (0.00, 0.000167),
    "H2": (0.00, 0.40),
    "O2": (0.00, 0.02),
    "CO": (0.00, 0.13),
    "H2O": (0.00, 0.0002),
    "H2S": (0.00, 0.27),
    "He": (0.00, 0.005),
    "Ar": (0.00, 0.0005),
}

DETAIL_BOUNDS = {"pressure_max": 350, "temperature_max": 177}
GERG_BOUNDS = {"pressure_max": 700, "temperature_max": 427}

COMBINED_RANGES = {
    "DETAIL": {
        ("iC4", "nC4"): (0.0, 0.015),
        ("iC5", "nC5"): (0.0, 0.005),
        ("nC8", "nC9", "nC10"): (0.0, 0.0005),
    },
    "GERG": {
        ("iC4", "nC4"): (0.0, 0.06),
        ("iC5", "nC5"): (0.0, 0.005),
        ("nC8", "nC9", "nC10"): (0.0, 0.0005),
    },
}


def render(composition: dict | None) -> None:
    """Render the composition validation tab."""
    st.subheader("Composition Quality Validation")

    if composition is None:
        st.info("Enter a gas composition in the table above to validate.")
        return

    if "validation_pressure" not in st.session_state:
        st.session_state.validation_pressure = 100.0
    if "validation_temperature" not in st.session_state:
        st.session_state.validation_temperature = 60.0

    col1, col2 = st.columns(2)
    with col1:
        pressure = st.number_input(
            "Pressure (bara)",
            value=st.session_state.validation_pressure,
            min_value=0.0,
            step=10.0,
        )
        st.session_state.validation_pressure = pressure

    with col2:
        temperature = st.number_input(
            "Temperature (°C)",
            value=st.session_state.validation_temperature,
            min_value=-50.0,
            step=5.0,
        )
        st.session_state.validation_temperature = temperature

    table_rows = []

    for display_name, symbol_combined in COMPONENTS_METADATA:
        if "+" in symbol_combined:
            symbols = symbol_combined.split("+")
            actual_pct = sum(composition.get(s, 0.0) for s in symbols)
            detail_min, detail_max = _get_combined_range(symbols, "DETAIL")
            gerg_min, gerg_max = _get_combined_range(symbols, "GERG")
        else:
            actual_pct = composition.get(symbol_combined, 0.0)
            detail_range = DETAIL_RANGES.get(symbol_combined, (None, None))
            gerg_range = GERG_RANGES.get(symbol_combined, (None, None))
            detail_min, detail_max = detail_range
            gerg_min, gerg_max = gerg_range

        detail_pass = None
        gerg_pass = None

        if detail_min is not None and detail_max is not None:
            detail_pass = detail_min * 100 <= actual_pct <= detail_max * 100

        if gerg_min is not None and gerg_max is not None:
            gerg_pass = gerg_min * 100 <= actual_pct <= gerg_max * 100

        detail_min_str = f"{detail_min*100:.2f}" if detail_min is not None else "—"
        detail_max_str = f"{detail_max*100:.2f}" if detail_max is not None else "—"
        gerg_min_str = f"{gerg_min*100:.2f}" if gerg_min is not None else "—"
        gerg_max_str = f"{gerg_max*100:.2f}" if gerg_max is not None else "—"

        detail_status = "✅" if detail_pass else "❌" if detail_pass is False else ""
        gerg_status = "✅" if gerg_pass else "❌" if gerg_pass is False else ""

        table_rows.append({
            "Component": display_name,
            "Symbol": symbol_combined,
            "DETAIL Min": detail_min_str,
            "DETAIL Max": detail_max_str,
            "DETAIL": detail_status,
            "GERG Min": gerg_min_str,
            "GERG Max": gerg_max_str,
            "GERG": gerg_status,
            "Actual": f"{actual_pct:.2f}",
        })

    detail_p_pass = 0 <= pressure <= DETAIL_BOUNDS["pressure_max"]
    gerg_p_pass = 0 <= pressure <= GERG_BOUNDS["pressure_max"]
    table_rows.append({
        "Component": "Pressure",
        "Symbol": "bar",
        "DETAIL Min": "0.00",
        "DETAIL Max": f"{DETAIL_BOUNDS['pressure_max']:.2f}",
        "DETAIL": "✅" if detail_p_pass else "❌",
        "GERG Min": "0.00",
        "GERG Max": f"{GERG_BOUNDS['pressure_max']:.2f}",
        "GERG": "✅" if gerg_p_pass else "❌",
        "Actual": f"{pressure:.2f}",
    })

    detail_t_pass = 0 <= temperature <= DETAIL_BOUNDS["temperature_max"]
    gerg_t_pass = 0 <= temperature <= GERG_BOUNDS["temperature_max"]
    table_rows.append({
        "Component": "Temperature",
        "Symbol": "°C",
        "DETAIL Min": "0",
        "DETAIL Max": str(DETAIL_BOUNDS["temperature_max"]),
        "DETAIL": "✅" if detail_t_pass else "❌",
        "GERG Min": "0",
        "GERG Max": str(GERG_BOUNDS["temperature_max"]),
        "GERG": "✅" if gerg_t_pass else "❌",
        "Actual": f"{temperature:.2f}",
    })

    st.markdown("""
    **Quality ranges defined in the AGA8 report no. 8 - part 2 (2017):**

    - **Pipeline Quality Range** – Applicable to the DETAIL method. Pressure ≤ 350 bara, Temperature ≤ 177°C.
    - **Intermediate Quality Range** – Applicable to the GERG-2008 method. Allows wider componsition, pressure and temperature ranges. Pressure ≤ 700 bara, Temperature ≤ 427°C.

    NB: The table below shows the composition ranges for the Pipeline and Intermediate quality ranges. The Pipeline quality range is labeled by DETAIL Min and Max and provides the value in mol%. The Intermediate quality range is labeled by GERG Min and Max and also provides the value in mol%. The Actual column shows the actual composition of the gas in mol%. The checkmarks indicate whether the actual composition falls within the specified ranges for each method.
    """)

    df = pd.DataFrame(table_rows)

    def color_status(val):
        """Format pass/fail markers for the validation table."""
        if val == "✅":
            return "color: green; font-weight: bold; font-size: 16px;"
        elif val == "❌":
            return "color: red; font-weight: bold; font-size: 16px;"
        return ""

    def color_actual(row):
        """Highlight the actual value based on validation status."""
        detail_status = row["DETAIL"]
        gerg_status = row["GERG"]

        if gerg_status == "❌":
            return "background-color: #ff6b6b; color: white; font-weight: bold;"
        elif detail_status == "❌":
            return "background-color: #ffd93d; color: black; font-weight: bold;"
        else:
            return "background-color: #a8e6cf; color: black;"

    styled = df.style.map(color_status, subset=["DETAIL", "GERG"])
    styled = styled.apply(lambda row: [color_actual(row) if col == "Actual" else "" for col in df.columns], axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True, height=35 + (len(table_rows) * 35))

    st.markdown("---")
    _display_validation_summary(composition, pressure, temperature)


def _get_combined_range(symbols: list[str], eos_model: str) -> tuple:
    """Return the combined limit range for grouped components."""
    key = tuple(symbols)
    group_range = COMBINED_RANGES.get(eos_model, {}).get(key)
    if group_range is not None:
        return group_range

    ranges = DETAIL_RANGES if eos_model == "DETAIL" else GERG_RANGES
    total_max = sum(ranges.get(s, (0, 0))[1] for s in symbols)
    return 0.0, total_max


def _display_validation_summary(composition: dict, pressure: float, temperature: float) -> None:
    """Show overall DETAIL and GERG validation status."""
    detail_comp_violations = 0
    gerg_comp_violations = 0

    for comp_name, symbol_combined in COMPONENTS_METADATA:
        if "+" in symbol_combined:
            symbols = symbol_combined.split("+")
            actual = sum(composition.get(s, 0.0) for s in symbols)
            detail_min, detail_max = _get_combined_range(symbols, "DETAIL")
            gerg_min, gerg_max = _get_combined_range(symbols, "GERG")
        else:
            actual = composition.get(symbol_combined, 0.0)
            detail_range = DETAIL_RANGES.get(symbol_combined, None)
            gerg_range = GERG_RANGES.get(symbol_combined, None)
            if detail_range:
                detail_min, detail_max = detail_range
            else:
                detail_min, detail_max = None, None
            if gerg_range:
                gerg_min, gerg_max = gerg_range
            else:
                gerg_min, gerg_max = None, None

        if detail_min is not None and detail_max is not None:
            if not (detail_min * 100 <= actual <= detail_max * 100):
                detail_comp_violations += 1

        if gerg_min is not None and gerg_max is not None:
            if not (gerg_min * 100 <= actual <= gerg_max * 100):
                gerg_comp_violations += 1

    detail_pt_ok = (0 <= pressure <= DETAIL_BOUNDS["pressure_max"] and
                    0 <= temperature <= DETAIL_BOUNDS["temperature_max"])
    gerg_pt_ok = (0 <= pressure <= GERG_BOUNDS["pressure_max"] and
                  0 <= temperature <= GERG_BOUNDS["temperature_max"])

    col1, col2 = st.columns(2)

    with col1:
        if detail_comp_violations == 0 and detail_pt_ok:
            st.success("✅ **DETAIL (Pipeline Quality):** IN RANGE")
        elif not detail_pt_ok:
            st.error("❌ **DETAIL:** Out of P/T bounds")
        else:
            st.warning(f"⚠️ **DETAIL:** {detail_comp_violations} component(s) out of range")

    with col2:
        if gerg_comp_violations == 0 and gerg_pt_ok:
            st.success("✅ **GERG-2008 (Intermediate Quality):** IN RANGE")
        elif not gerg_pt_ok:
            st.error("❌ **GERG-2008:** Out of P/T bounds")
        else:
            st.warning(f"⚠️ **GERG-2008:** {gerg_comp_violations} component(s) out of range")
