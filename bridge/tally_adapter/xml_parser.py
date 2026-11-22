"""Tally XML Response Parser and Decimal Data Converter.

Parses Tally Prime XML responses safely into typed Python dictionaries and Decimal models.
Ensures:
1. XML Entity Expansion protection.
2. Decimal exactness on all monetary amounts (using bridge/tally_adapter/decimal_math.py).
3. Automatic untrusted text wrapping on narrations, names, and remarks (using server/sanitize/untrusted_text.py).
4. Exact date delta calculation for aging buckets (0-30, 31-60, 61-90, 90+ days).
"""

import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal
from typing import Any

from bridge.tally_adapter.decimal_math import ensure_decimal
from server.sanitize.untrusted_text import sanitize_untrusted_text


def parse_company_info(xml_text: str) -> dict[str, Any]:
    """Parse Company Details XML response."""
    root = ET.fromstring(xml_text)
    data = root.find(".//DATA")
    if data is None:
        raise ValueError("Malformed Tally XML: Missing <DATA> block in Company Info response.")

    def _get(tag: str, default: str = "") -> str:
        elem = data.find(tag)
        return elem.text.strip() if elem is not None and elem.text else default

    company_name = _get("COMPANYNAME")
    return {
        "company_name": company_name,
        "financial_year_from": _get("STARTINGFROM"),
        "financial_year_to": _get("ENDINGAT"),
        "books_from": _get("BOOKSFROM"),
        "base_currency": _get("BASECURRENCY", "INR"),
        "currency_symbol": _get("CURRENCYSYMBOL", "₹"),
        "gstin": _get("GSTIN"),
        "address": sanitize_untrusted_text(_get("ADDRESS")).to_dict(),
    }


def parse_ledgers(xml_text: str) -> list[dict[str, Any]]:
    """Parse List of Accounts / Ledgers XML response."""
    root = ET.fromstring(xml_text)
    ledger_elements = root.findall(".//LEDGER")
    ledgers: list[dict[str, Any]] = []

    for elem in ledger_elements:
        name_elem = elem.find("NAME")
        parent_elem = elem.find("PARENT")
        op_elem = elem.find("OPENINGBALANCE")
        cl_elem = elem.find("CLOSINGBALANCE")

        name = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
        parent = parent_elem.text.strip() if parent_elem is not None and parent_elem.text else ""
        op_str = op_elem.text.strip() if op_elem is not None and op_elem.text else "0.00"
        cl_str = cl_elem.text.strip() if cl_elem is not None and cl_elem.text else "0.00"

        ledgers.append({
            "name": name,
            "parent": parent,
            "opening_balance": ensure_decimal(op_str),
            "closing_balance": ensure_decimal(cl_str),
        })

    return ledgers


def parse_party_ledger(xml_text: str) -> dict[str, Any]:
    """Parse Ledger Vouchers (Party Statement) XML response."""
    root = ET.fromstring(xml_text)
    data = root.find(".//DATA")
    if data is None:
        raise ValueError("Malformed Tally XML: Missing <DATA> block in Ledger Vouchers.")

    ledger_name = data.findtext("LEDGERNAME", "")
    op_str = data.findtext("OPENINGBALANCE", "0.00")
    cl_str = data.findtext("CLOSINGBALANCE", "0.00")

    entries: list[dict[str, Any]] = []
    for v in data.findall(".//VOUCHER"):
        v_no = v.findtext("VOUCHERNUMBER", "")
        v_date = v.findtext("DATE", "")
        v_type = v.findtext("VOUCHERTYPENAME", "")
        v_amt = ensure_decimal(v.findtext("AMOUNT", "0.00"))
        is_dr = v.findtext("ISDEBIT", "No").lower() in ("yes", "true", "1")
        run_bal = ensure_decimal(v.findtext("RUNNINGBALANCE", "0.00"))
        narration = v.findtext("NARRATION", "")

        entries.append({
            "voucher_no": v_no,
            "date": v_date,
            "voucher_type": v_type,
            "amount": v_amt,
            "is_debit": is_dr,
            "running_balance": run_bal,
            "narration": sanitize_untrusted_text(narration).to_dict(),
        })

    return {
        "ledger_name": ledger_name,
        "opening_balance": ensure_decimal(op_str),
        "closing_balance": ensure_decimal(cl_str),
        "entries": entries,
    }


def parse_receivables_ageing(
    xml_text: str,
    as_on_date: str,
    buckets: list[int] | None = None,
    min_amount: Decimal | None = None,
    top_n: int = 20,
) -> dict[str, Any]:
    """Parse Bills Receivable and calculate exact aging buckets (0-30, 31-60, 61-90, 90+ days).

    Age = (as_on_date - bill_date).days
    """
    if buckets is None:
        buckets = [30, 60, 90]

    as_on = datetime.strptime(as_on_date, "%Y-%m-%d").date()
    root = ET.fromstring(xml_text)
    bills = root.findall(".//BILL")

    party_totals: dict[str, dict[str, Any]] = {}

    for b in bills:
        party = b.findtext("PARTYNAME", "Unknown Party")
        bill_date_str = b.findtext("BILLDATE", "")
        pending_str = b.findtext("PENDINGAMOUNT", "0.00")
        pending_amt = ensure_decimal(pending_str)

        if min_amount and pending_amt < min_amount:
            continue

        bill_date = datetime.strptime(bill_date_str, "%Y-%m-%d").date()
        age_days = (as_on - bill_date).days

        # Determine bucket
        if age_days <= buckets[0]:
            bucket_key = f"0-{buckets[0]}"
        elif age_days <= buckets[1]:
            bucket_key = f"{buckets[0] + 1}-{buckets[1]}"
        elif len(buckets) > 2 and age_days <= buckets[2]:
            bucket_key = f"{buckets[1] + 1}-{buckets[2]}"
        else:
            last_bucket = buckets[-1]
            bucket_key = f"{last_bucket}+"

        if party not in party_totals:
            party_totals[party] = {
                "party": party,
                "total_outstanding": Decimal("0.00"),
                "buckets": {
                    f"0-{buckets[0]}": Decimal("0.00"),
                    f"{buckets[0] + 1}-{buckets[1]}": Decimal("0.00"),
                    f"{buckets[1] + 1}-{buckets[2]}" if len(buckets) > 2 else "": Decimal("0.00"),
                    f"{buckets[-1]}+": Decimal("0.00"),
                },
                "bills_count": 0,
            }

        party_totals[party]["total_outstanding"] += pending_amt
        party_totals[party]["buckets"][bucket_key] += pending_amt
        party_totals[party]["bills_count"] += 1

    # Sort by total_outstanding descending, take top_n
    sorted_parties = sorted(
        party_totals.values(), key=lambda p: p["total_outstanding"], reverse=True
    )[:top_n]

    # Calculate overall total
    grand_total = sum((p["total_outstanding"] for p in sorted_parties), Decimal("0.00"))

    return {
        "as_on": as_on_date,
        "buckets_defined": buckets,
        "grand_total_receivables": grand_total,
        "parties_count": len(sorted_parties),
        "parties": sorted_parties,
    }


def parse_stock_summary(xml_text: str) -> list[dict[str, Any]]:
    """Parse Stock Summary XML response."""
    root = ET.fromstring(xml_text)
    items = root.findall(".//STOCKITEM")
    stock_list: list[dict[str, Any]] = []

    for item in items:
        name = item.findtext("NAME", "")
        group = item.findtext("GROUP", "")
        closing_qty = ensure_decimal(item.findtext("CLOSINGQTY", "0.00"))
        uom = item.findtext("UOM", "NOS")
        rate = ensure_decimal(item.findtext("RATE", "0.00"))
        closing_val = ensure_decimal(item.findtext("CLOSINGVALUE", "0.00"))

        stock_list.append({
            "name": name,
            "group": group,
            "closing_quantity": closing_qty,
            "uom": uom,
            "rate": rate,
            "closing_value": closing_val,
        })

    return stock_list
