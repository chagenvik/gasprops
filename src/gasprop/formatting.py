"""
Shared number formatting for the Gas Properties module.

Engineering results in this app span many orders of magnitude — from a discharge
coefficient of 0.6 to a Reynolds number of 8.2e6 to millions of Sm3/d. A fixed number
of decimals is therefore either noise (``0.600000`` for beta) or a loss of resolution.
:func:`format_value` keeps a roughly constant number of significant digits and drops
trailing zeros, so every quantity reads naturally without per-call formatting rules.
"""

from __future__ import annotations

import math

#: Shown instead of a number when a value is missing or not finite.
NOT_AVAILABLE = "–"

#: Above this magnitude, and below its reciprocal-ish counterpart, switch to scientific.
_SCIENTIFIC_UPPER = 1.0e9
_SCIENTIFIC_LOWER = 1.0e-4


def format_value(value: float | None, significant: int = 6) -> str:
    """Format a number with ``significant`` significant digits and no trailing zeros.

    Examples
    --------
    >>> format_value(0.6)
    '0.6'
    >>> format_value(58736.1044)
    '58,736.1'
    >>> format_value(8206300.0)
    '8,206,300'
    """
    if value is None:
        return NOT_AVAILABLE

    try:
        number = float(value)
    except (TypeError, ValueError):
        return NOT_AVAILABLE

    if not math.isfinite(number):
        return NOT_AVAILABLE
    if number == 0.0:
        return "0"

    magnitude = abs(number)
    if magnitude >= _SCIENTIFIC_UPPER or magnitude < _SCIENTIFIC_LOWER:
        return f"{number:.4e}"

    if magnitude >= 1.0:
        integer_digits = int(math.floor(math.log10(magnitude))) + 1
        decimals = max(0, significant - integer_digits)
    else:
        # Leading zeros after the decimal point do not count as significant digits.
        leading_zeros = int(math.floor(-math.log10(magnitude)))
        decimals = significant + leading_zeros

    text = f"{number:,.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
