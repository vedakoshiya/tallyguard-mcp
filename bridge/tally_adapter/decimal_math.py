"""Decimal Currency Mathematics Engine for TallyGuard MCP.

Strictly enforces decimal precision (to the exact paisa, 2 decimal places) using Python's
`decimal.Decimal` and `ROUND_HALF_UP`. Rejects any `float` input to prevent binary floating-point
inaccuracies.
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Two decimal places for currency quantization (exact paisa)
CURRENCY_QUANTIZATION = Decimal("0.01")


def ensure_decimal(value: str | int | Decimal) -> Decimal:
    """Ensure value is converted to a strict Decimal.

    Raises:
        TypeError: If a float or unsupported type is passed.
        ValueError: If string cannot be parsed as a valid numeric amount.
    """
    if isinstance(value, float):
        raise TypeError(
            f"Floating-point values ({value}) are strictly forbidden in TallyGuard financial "
            f"calculations to prevent precision loss. Use Decimal, int, or str."
        )

    if isinstance(value, Decimal):
        return quantize_currency(value)

    if isinstance(value, int):
        return quantize_currency(Decimal(value))

    if isinstance(value, str):
        # Clean currency symbols, commas, spaces
        cleaned = value.strip().replace(",", "")
        cleaned = re.sub(r"^[₹$Rs\.\s]+", "", cleaned, flags=re.IGNORECASE)

        # Detect Dr / Cr suffixes commonly used in Tally XML
        is_cr = False
        if cleaned.upper().endswith(" DR"):
            cleaned = cleaned[:-3].strip()
        elif cleaned.upper().endswith(" CR"):
            is_cr = True
            cleaned = cleaned[:-3].strip()

        try:
            d = Decimal(cleaned)
            # In Tally convention, Debit is positive, Credit is negative in ledger balances,
            # or vice-versa depending on context. We preserve the sign or adjust by flag:
            if is_cr and d > 0:
                d = -d
            return quantize_currency(d)
        except InvalidOperation as e:
            raise ValueError(f"Cannot parse '{value}' as a valid monetary Decimal amount.") from e

    raise TypeError(
        f"Unsupported monetary value type: {type(value).__name__}. Expected Decimal, int, or str."
    )


def quantize_currency(val: Decimal) -> Decimal:
    """Quantize any Decimal value to 2 decimal places using ROUND_HALF_UP."""
    return val.quantize(CURRENCY_QUANTIZATION, rounding=ROUND_HALF_UP)


def to_paise(val: str | int | Decimal) -> int:
    """Convert a monetary currency value into integer paise (e.g. 150.75 -> 15075)."""
    d = ensure_decimal(val)
    return int(d * 100)


def from_paise(paise: int) -> Decimal:
    """Convert integer paise back into a 2-decimal-place Decimal (e.g. 15075 -> 150.75)."""
    if not isinstance(paise, int):
        raise TypeError(f"Paise value must be an integer, got {type(paise).__name__}.")
    return quantize_currency(Decimal(paise) / Decimal(100))


def format_inr(val: str | int | Decimal, include_symbol: bool = True) -> str:
    """Format a Decimal amount using the Indian numbering system (e.g. 1,23,456.78).

    Indian grouping: last 3 digits grouped, then groups of 2 digits.
    """
    d = ensure_decimal(val)
    is_negative = d < 0
    abs_d = abs(d)

    parts = f"{abs_d:.2f}".split(".")
    integer_part = parts[0]
    decimal_part = parts[1]

    if len(integer_part) > 3:
        last_three = integer_part[-3:]
        remaining = integer_part[:-3]
        # Group remaining digits in pairs of 2 from right to left
        grouped_pairs = []
        while len(remaining) > 2:
            grouped_pairs.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            grouped_pairs.insert(0, remaining)
        formatted_int = ",".join(grouped_pairs) + "," + last_three
    else:
        formatted_int = integer_part

    result = f"{formatted_int}.{decimal_part}"
    if is_negative:
        result = f"-{result}"

    if include_symbol:
        return f"₹{result}"
    return result
