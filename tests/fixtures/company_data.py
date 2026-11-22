"""Surat Textile Traders Reference Fixture Company Dataset.

Provides exact ground-truth financial records for TallyGuard MCP testing,
ensuring exact paisa reconciliation across ledgers, vouchers, ageing, stock, and tax.
"""

from decimal import Decimal
from typing import Any, Dict, List

COMPANY_METADATA: Dict[str, Any] = {
    "name": "Surat Textile Traders Pvt Ltd",
    "financial_year_from": "2026-04-01",
    "financial_year_to": "2027-03-31",
    "books_from": "2026-04-01",
    "base_currency": "INR",
    "currency_symbol": "₹",
    "address": "Ring Road, Surat, Gujarat - 395002",
    "gstin": "24AAACS1234F1Z5",
}

# Chart of Accounts with exact balances
CHART_OF_ACCOUNTS: List[Dict[str, Any]] = [
    {
        "name": "Cash in Hand",
        "parent": "Cash-in-Hand",
        "opening_balance": Decimal("50000.00"),
        "closing_balance": Decimal("65000.00"),
        "is_debit": True,
    },
    {
        "name": "HDFC Bank",
        "parent": "Bank Accounts",
        "opening_balance": Decimal("500000.00"),
        "closing_balance": Decimal("670000.00"),
        "is_debit": True,
    },
    {
        "name": "Patel Textiles",
        "parent": "Sundry Debtors",
        "opening_balance": Decimal("150000.00"),
        "closing_balance": Decimal("180000.00"),
        "is_debit": True,
    },
    {
        "name": "Surat Silk Mills",
        "parent": "Sundry Debtors",
        "opening_balance": Decimal("80000.00"),
        "closing_balance": Decimal("120000.00"),
        "is_debit": True,
    },
    {
        "name": "Vardhman Yarns",
        "parent": "Sundry Creditors",
        "opening_balance": Decimal("200000.00"),
        "closing_balance": Decimal("140000.00"),
        "is_debit": False,  # Credit balance
    },
    {
        "name": "Gujarat Dyeing Works",
        "parent": "Sundry Creditors",
        "opening_balance": Decimal("90000.00"),
        "closing_balance": Decimal("50000.00"),
        "is_debit": False,  # Credit balance
    },
    {
        "name": "Sales Account",
        "parent": "Sales Accounts",
        "opening_balance": Decimal("0.00"),
        "closing_balance": Decimal("450000.00"),
        "is_debit": False,
    },
    {
        "name": "Purchase Account",
        "parent": "Purchase Accounts",
        "opening_balance": Decimal("0.00"),
        "closing_balance": Decimal("280000.00"),
        "is_debit": True,
    },
    {
        "name": "CGST",
        "parent": "Duties & Taxes",
        "opening_balance": Decimal("0.00"),
        "closing_balance": Decimal("11250.00"),
        "is_debit": False,
    },
    {
        "name": "SGST",
        "parent": "Duties & Taxes",
        "opening_balance": Decimal("0.00"),
        "closing_balance": Decimal("11250.00"),
        "is_debit": False,
    },
]

# Detailed Vouchers
SAMPLE_VOUCHERS: List[Dict[str, Any]] = [
    {
        "voucher_no": "SAL-001",
        "voucher_type": "Sales",
        "date": "2026-05-10",
        "party": "Patel Textiles",
        "amount": Decimal("100000.00"),
        "narration": "Sales of cotton grey fabric against PO #4521",
        "lines": [
            {"ledger": "Patel Textiles", "amount": Decimal("100000.00"), "is_debit": True},
            {"ledger": "Sales Account", "amount": Decimal("100000.00"), "is_debit": False},
        ],
    },
    {
        "voucher_no": "REC-001",
        "voucher_type": "Receipt",
        "date": "2026-06-15",
        "party": "Patel Textiles",
        "amount": Decimal("70000.00"),
        "narration": "NEFT received from Patel Textiles towards part payment",
        "lines": [
            {"ledger": "HDFC Bank", "amount": Decimal("70000.00"), "is_debit": True},
            {"ledger": "Patel Textiles", "amount": Decimal("70000.00"), "is_debit": False},
        ],
    },
    {
        "voucher_no": "SAL-002",
        "voucher_type": "Sales",
        "date": "2026-08-20",
        "party": "Surat Silk Mills",
        "amount": Decimal("90000.00"),
        "narration": "Dispatch of pure silk fabric batch #882",
        "lines": [
            {"ledger": "Surat Silk Mills", "amount": Decimal("90000.00"), "is_debit": True},
            {"ledger": "Sales Account", "amount": Decimal("90000.00"), "is_debit": False},
        ],
    },
    {
        "voucher_no": "PAY-001",
        "voucher_type": "Payment",
        "date": "2026-07-02",
        "party": "Vardhman Yarns",
        "amount": Decimal("60000.00"),
        "narration": "RTGS payment to Vardhman Yarns for yarn supply",
        "lines": [
            {"ledger": "Vardhman Yarns", "amount": Decimal("60000.00"), "is_debit": True},
            {"ledger": "HDFC Bank", "amount": Decimal("60000.00"), "is_debit": False},
        ],
    },
]

# Receivables Outstanding Bills (as of 2026-10-31)
RECEIVABLES_BILLS: List[Dict[str, Any]] = [
    {
        "bill_no": "INV-2026-01",
        "party": "Patel Textiles",
        "bill_date": "2026-05-10",
        "due_date": "2026-06-10",
        "original_amount": Decimal("100000.00"),
        "pending_amount": Decimal("30000.00"),
        # Age as of 2026-10-31: ~143 days -> 90+ days bucket
    },
    {
        "bill_no": "INV-2026-02",
        "party": "Patel Textiles",
        "bill_date": "2026-09-01",
        "due_date": "2026-10-01",
        "original_amount": Decimal("150000.00"),
        "pending_amount": Decimal("150000.00"),
        # Age as of 2026-10-31: 60 days -> 31-60 days bucket
    },
    {
        "bill_no": "INV-2026-03",
        "party": "Surat Silk Mills",
        "bill_date": "2026-10-15",
        "due_date": "2026-11-15",
        "original_amount": Decimal("120000.00"),
        "pending_amount": Decimal("120000.00"),
        # Age as of 2026-10-31: 16 days -> 0-30 days bucket
    },
]

# Stock Summary
STOCK_ITEMS: List[Dict[str, Any]] = [
    {
        "name": "Cotton Grey Fabric 40s",
        "group": "Fabric",
        "closing_qty": Decimal("1500.00"),
        "uom": "MTR",
        "rate": Decimal("120.00"),
        "closing_value": Decimal("180000.00"),
    },
    {
        "name": "Silk Chiffon 60g",
        "group": "Silk",
        "closing_qty": Decimal("800.00"),
        "uom": "MTR",
        "rate": Decimal("350.00"),
        "closing_value": Decimal("280000.00"),
    },
    {
        "name": "Polyester Georgette",
        "group": "Synthetics",
        "closing_qty": Decimal("2500.00"),
        "uom": "MTR",
        "rate": Decimal("85.00"),
        "closing_value": Decimal("212500.00"),
    },
]
