# gasprops

Streamlit app for gas property analysis using AGA8 and NeqSim workflows.

## Run locally

```bash
streamlit run streamlit_app.py
```

## App layout

- **Tabbed views** for all gas-property pages
- **Shared AGA8 composition editor** at the top of the app
- **Direct use of `pvtlib`, `neqsim-python`, and `uncertaintylib`**
- The AGA8 DETAIL and GERG-2008 implementations used through `pvtlib` are based on the official [NIST AGA8 reference repository](https://github.com/usnistgov/AGA8), via the Rust [aga8 crate](https://crates.io/crates/aga8)

## Calculation Scope

- **AGA8 DETAIL / GERG-2008 (primary engine):** Used for most property workflows (single-point, multi-point, tables, surfaces, uncertainty, comparison, validation, and mixing). These calculations are intended for **single-phase gas**.
- **NeqSim workflows:** Used in **Flash Calculation** and **Phase Envelope** tabs for phase-behavior analysis.
- **Composition constraint:** The app input is constrained to the **21-component AGA8 component set**.

## Included views

- Single Calculation
- Multi-Point Calculation
- Flash Calculation
- Phase Envelope
- Mix
- Property Tables
- 3D plot
- Uncertainty Analysis
- AGA8 EoS Comparison
- AGA8 Validation

## Repository structure

```text
streamlit_app.py
src/gasprop/
data/examples/
tests/
```

## Notes

- Example gas compositions are bundled in `data/examples/`.
- Imported compositions are normalized to the AGA8 composition table used by the original app.
- The app is designed for Streamlit Community Cloud.
- NeqSim-backed views require Java on the deployment target; Streamlit Cloud support is configured via `packages.txt`.

## Legal

- This app is provided **as-is**, without warranty.
- It is for informational use only and is **not** a certified engineering or operational decision tool.
- Users are responsible for independent verification before any safety-critical, operational, financial, or regulatory use.
- Terms of Use: see [TERMS_OF_USE.md](TERMS_OF_USE.md).
- License: MIT (see [LICENSE](LICENSE)).
