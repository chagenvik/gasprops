# Copilot Instructions for gasprops

## Purpose
This application is an engineering tool. The primary goal is accurate, verifiable calculations for gas properties and related workflows.

## Testing Strategy (Required)
- Use `pytest` for all tests.
- Write tests as simple, readable functions.
- Do not use test classes for normal unit tests.
- Prefer explicit test functions over abstractions that hide behavior.
- Keep test setup minimal and local to the test.
- Test names must clearly describe behavior and expected outcome.

## Debuggability (Required)
- Tests must be easy to debug line-by-line in VS Code.
- Avoid patterns that make breakpoints hard to hit or reason about.
- Prefer straightforward assertions over complex helper layers.
- Keep one clear behavior per test whenever practical.
- Preserve deterministic inputs and outputs.

## Validation Philosophy
- Validate both pass and fail boundaries.
- Validate exact expected outputs for critical engineering calculations.
- For validation/range logic, assert both:
  - number of issues
  - which specific issue names/components failed
- Add regression tests for previously discovered edge cases.

## Numerical/Engineering Expectations
- Use stable tolerances (`pytest.approx`) when comparing floating-point results.
- Keep reference-case tests for known compositions and expected outputs.
- Any logic change that affects calculations must be accompanied by tests.

## CI Expectations
- Test suite must run in GitHub Actions on pull requests and pushes to `main`.
- New features are not complete until tests are added and passing.

## Code Style for Tests
- Keep test code plain and readable.
- Avoid unnecessary indirection, inheritance, or meta-programming in tests.
- Favor clarity over cleverness.
