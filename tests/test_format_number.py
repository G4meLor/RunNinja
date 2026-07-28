"""Tests for ``utils.format_number``: overflow fallback + tiered precision.

Covers:
- Small numbers render as plain integers (0, 123).
- 1e3..1e6 tier uses 2 decimals (e.g. ``1.23k``, ``1.50M``).
- >=1e9 tier uses 2 significant figures (e.g. ``1.5B``, ``12B``).
- Beyond the unit table (>=1e36) rolls to scientific notation instead of
  the old ``1000Dc`` overflow.
- ``None`` and negatives are handled.
"""
from utils import format_number


def test_small_numbers():
    assert format_number(0) == "0"
    assert format_number(123) == "123"
    # 2 decimals in the <1e6 tier; lowercase "k" matches the existing unit table.
    assert format_number(1234) == "1.23k"


def test_large_numbers_tiered():
    # <1e9 tier -> 2 decimals.
    assert format_number(1_500_000) == "1.50M"
    # >=1e9 tier -> 2 significant figures (no trailing zero).
    assert format_number(1_500_000_000) == "1.5B"
    assert format_number(12_300_000_000) == "12B"


def test_overflow_scientific_notation():
    # 1e36 must NOT return "1000Dc"; it rolls to scientific notation.
    s = format_number(1e36)
    assert "e" in s.lower(), f"expected scientific notation, got {s!r}"
    assert "Dc" not in s, f"overflow at 1e36: {s!r}"

    # 1e40 -> scientific as well.
    s2 = format_number(1e40)
    assert "e" in s2.lower(), f"expected scientific notation, got {s2!r}"
    assert "Dc" not in s2, f"overflow at 1e40: {s2!r}"

    # Boundary just below overflow still uses the last unit (Dc).
    assert format_number(5e35) == "500Dc"


def test_negative_and_none():
    assert format_number(None) == "0"
    assert format_number(-1234) == "-1.23k"
    assert format_number(-1_500_000) == "-1.50M"
    assert format_number(-1e36) == "-1.00e+36"
