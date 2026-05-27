# gasprops

Standalone Streamlit app for gas property analysis.

## Run locally

```bash
streamlit run streamlit_app.py
```

## App layout

- **Left sidebar navigation** for all gas-property views
- **Shared AGA8 composition editor** at the top of the app
- **Direct use of `pvtlib`, `neqsim`, and `uncertaintylib`**

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

## Legal

- This app is provided **as-is**, without warranty.
- It is for informational use only and is **not** a certified engineering or operational decision tool.
- Users are responsible for independent verification before any safety-critical, operational, financial, or regulatory use.
- License: MIT (see [LICENSE](LICENSE)).
