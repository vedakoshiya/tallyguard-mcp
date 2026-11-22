"""Automated Exact Paisa Reconciliation Test Suite for TallyGuard MCP.

Satisfies Goal G1: Asserts that all read tools and queries reconcile to the exact paisa
against Tally reference fixture data without floating-point inaccuracies.
Uses in-memory simulated Tally transport for rapid, deterministic execution.
"""

from decimal import Decimal
import pytest
import httpx

from tests.fixtures.company_data import (
    COMPANY_METADATA,
    CHART_OF_ACCOUNTS,
)
from tests.simulated_tally.server import create_simulated_tally_transport
from bridge.tally_adapter.client import TallyAdapterClient, TallyConnectionError


@pytest.fixture
def client():
    """Provide a TallyAdapterClient wired to the simulated Tally engine."""
    transport = create_simulated_tally_transport()
    return TallyAdapterClient(transport=transport)


def test_reconcile_company_info(client):
    """Assert company identity, financial year, and base currency match ground truth."""
    info = client.get_company_info()

    assert info["company_name"] == COMPANY_METADATA["name"]
    assert info["financial_year_from"] == COMPANY_METADATA["financial_year_from"]
    assert info["financial_year_to"] == COMPANY_METADATA["financial_year_to"]
    assert info["base_currency"] == "INR"
    assert info["currency_symbol"] == "₹"
    assert info["gstin"] == "24AAACS1234F1Z5"


def test_reconcile_chart_of_accounts(client):
    """Assert all ledger opening and closing balances match reference fixture to the paisa."""
    ledgers = client.list_ledgers()
    assert len(ledgers) == len(CHART_OF_ACCOUNTS)

    ledger_map = {l["name"]: l for l in ledgers}

    # Verify Patel Textiles
    patel = ledger_map["Patel Textiles"]
    assert patel["parent"] == "Sundry Debtors"
    assert patel["opening_balance"] == Decimal("150000.00")
    assert patel["closing_balance"] == Decimal("180000.00")

    # Verify HDFC Bank
    hdfc = ledger_map["HDFC Bank"]
    assert hdfc["opening_balance"] == Decimal("500000.00")
    assert hdfc["closing_balance"] == Decimal("670000.00")

    # Verify Vardhman Yarns (Credit balance)
    vardhman = ledger_map["Vardhman Yarns"]
    assert vardhman["closing_balance"] == Decimal("-140000.00")


def test_reconcile_party_ledger_statement(client):
    """Assert party voucher entries, debit/credit lines, and running balances match to the paisa."""
    stmt = client.get_party_ledger(
        party_name="Patel Textiles",
        from_date="2026-04-01",
        to_date="2026-10-31",
    )

    assert stmt["ledger_name"] == "Patel Textiles"
    assert stmt["opening_balance"] == Decimal("150000.00")
    assert stmt["closing_balance"] == Decimal("180000.00")

    entries = stmt["entries"]
    assert len(entries) == 2

    # Entry 1: Sales voucher for 1,00,000.00
    e1 = entries[0]
    assert e1["voucher_no"] == "SAL-001"
    assert e1["voucher_type"] == "Sales"
    assert e1["amount"] == Decimal("100000.00")
    assert e1["is_debit"] is True
    assert e1["running_balance"] == Decimal("250000.00")
    # Verify untrusted text wrapper
    assert "untrusted_text" in e1["narration"]
    assert e1["narration"]["untrusted_text"]["content"] == "Sales of cotton grey fabric against PO #4521"

    # Entry 2: Receipt voucher for 70,000.00
    e2 = entries[1]
    assert e2["voucher_no"] == "REC-001"
    assert e2["voucher_type"] == "Receipt"
    assert e2["amount"] == Decimal("70000.00")
    assert e2["is_debit"] is False
    assert e2["running_balance"] == Decimal("180000.00")


def test_reconcile_receivables_ageing(client):
    """Assert receivables aging buckets match exactly to the paisa."""
    ageing = client.get_receivables_ageing(
        as_on_date="2026-10-31",
        buckets=[30, 60, 90],
    )

    assert ageing["as_on"] == "2026-10-31"
    assert ageing["parties_count"] == 2
    assert ageing["grand_total_receivables"] == Decimal("300000.00")

    parties = {p["party"]: p for p in ageing["parties"]}

    # Patel Textiles: 30,000 in 90+ bucket, 150,000 in 31-60 bucket
    patel = parties["Patel Textiles"]
    assert patel["total_outstanding"] == Decimal("180000.00")
    assert patel["buckets"]["31-60"] == Decimal("150000.00")
    assert patel["buckets"]["90+"] == Decimal("30000.00")
    assert patel["buckets"]["0-30"] == Decimal("0.00")

    # Surat Silk Mills: 120,000 in 0-30 bucket
    surat_silk = parties["Surat Silk Mills"]
    assert surat_silk["total_outstanding"] == Decimal("120000.00")
    assert surat_silk["buckets"]["0-30"] == Decimal("120000.00")


def test_reconcile_stock_summary(client):
    """Assert inventory stock items and closing valuation reconcile to the paisa."""
    stock = client.get_stock_summary(as_on_date="2026-10-31")
    assert len(stock) == 3

    stock_map = {item["name"]: item for item in stock}

    item1 = stock_map["Cotton Grey Fabric 40s"]
    assert item1["closing_quantity"] == Decimal("1500.00")
    assert item1["rate"] == Decimal("120.00")
    assert item1["closing_value"] == Decimal("180000.00")

    item2 = stock_map["Silk Chiffon 60g"]
    assert item2["closing_value"] == Decimal("280000.00")

    total_stock_value = sum((item["closing_value"] for item in stock), Decimal("0.00"))
    assert total_stock_value == Decimal("672500.00")


def test_graceful_offline_handling():
    """Verify that an unreachable Tally transport raises TallyConnectionError."""
    def offline_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    offline_client = TallyAdapterClient(transport=httpx.MockTransport(offline_handler))
    with pytest.raises(TallyConnectionError, match="TALLY_UNAVAILABLE"):
        offline_client.get_company_info()
