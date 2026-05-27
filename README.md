# gasprops

Streamlit app for gas property analysis.

## Run locally

```bash
streamlit run streamlit_app.py
```

## App layout

- **Tabbed views** for all gas-property pages
- **Shared AGA8 composition editor** at the top of the app
- **Direct use of `pvtlib`, `neqsim-python`, and `uncertaintylib`**
- The AGA8 DETAIL and GERG-2008 implementations used through `pvtlib` are based on the official [NIST AGA8 reference repository](https://github.com/usnistgov/AGA8), via the Rust [aga8 crate](https://crates.io/crates/aga8)

## Included views

- Single Calculation
- Multi-Point Calculation
- Flash Calculation
- Property Tables
- 3D plot
- Phase Envelope
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
