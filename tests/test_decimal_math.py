"""Unit tests for decimal currency math engine."""

from decimal import Decimal
import pytest
from bridge.tally_adapter.decimal_math import (
    ensure_decimal,
    quantize_currency,
    to_paise,
    from_paise,
    format_inr,
)


def test_float_rejection():
    """Ensure floats are strictly rejected to prevent binary floating point inaccuracies."""
    with pytest.raises(TypeError, match="Floating-point values.*strictly forbidden"):
        ensure_decimal(123.45)

    with pytest.raises(TypeError, match="Floating-point values.*strictly forbidden"):
        ensure_decimal(0.0)

    with pytest.raises(TypeError, match="Floating-point values.*strictly forbidden"):
        to_paise(99.99)


def test_ensure_decimal_valid_types():
    """Test Decimal, integer, and string inputs."""
    assert ensure_decimal(Decimal("100.50")) == Decimal("100.50")
    assert ensure_decimal(500) == Decimal("500.00")
    assert ensure_decimal("1234.56") == Decimal("1234.56")
    assert ensure_decimal("  ₹ 50,000.00  ") == Decimal("50000.00")
    assert ensure_decimal("Rs. 1,23,456.78") == Decimal("123456.78")


def test_tally_dr_cr_suffixes():
    """Test Tally ledger balance suffixes."""
    assert ensure_decimal("25000.00 Dr") == Decimal("25000.00")
    assert ensure_decimal("18500.25 Cr") == Decimal("-18500.25")
    assert ensure_decimal("1,50,000.00 CR") == Decimal("-150000.00")


def test_quantize_rounding():
    """Verify ROUND_HALF_UP rules."""
    assert quantize_currency(Decimal("10.005")) == Decimal("10.01")
    assert quantize_currency(Decimal("10.004")) == Decimal("10.00")
    assert quantize_currency(Decimal("10.0051")) == Decimal("10.01")


def test_paise_conversions():
    """Test round-trip conversion to and from integer paise."""
    assert to_paise("150.75") == 15075
    assert to_paise(Decimal("25000.00")) == 2500000
    assert to_paise(0) == 0

    assert from_paise(15075) == Decimal("150.75")
    assert from_paise(2500000) == Decimal("25000.00")
    assert from_paise(0) == Decimal("0.00")

    with pytest.raises(TypeError):
        from_paise("100")  # type: ignore


def test_format_inr():
    """Verify Indian numbering format (1,23,456.78)."""
    assert format_inr("1000", include_symbol=False) == "1,000.00"
    assert format_inr("10000", include_symbol=False) == "10,000.00"
    assert format_inr("100000", include_symbol=False) == "1,00,000.00"
    assert format_inr("1234567.89", include_symbol=True) == "₹12,34,567.89"
    assert format_inr("-50000.00", include_symbol=True) == "₹-50,000.00"
    assert format_inr("50", include_symbol=True) == "₹50.00"
    assert format_inr(Decimal("99999999.99"), include_symbol=False) == "9,99,99,999.99"


def test_invalid_strings():
    """Verify malformed input rejection."""
    with pytest.raises(ValueError, match="Cannot parse.*valid monetary"):
        ensure_decimal("abc")

    with pytest.raises(ValueError, match="Cannot parse.*valid monetary"):
        ensure_decimal("12.34.56")
