"""Unit and schema validation tests for MCP Read Tools."""

import pytest
from pydantic import ValidationError

from bridge.tally_adapter.client import TallyAdapterClient
from server.mcp.tools.read_tools import ReadToolsHandler
from tests.simulated_tally.server import create_simulated_tally_transport


@pytest.fixture
def handler():
    """Create ReadToolsHandler connected to in-memory simulated Tally."""
    client = TallyAdapterClient(transport=create_simulated_tally_transport())
    return ReadToolsHandler(client)


def test_schema_rejects_extra_fields(handler):
    """Verify FR-082: Rejection of unknown properties to prevent injection."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        handler.get_company_info({"malicious_extra_field": "injected_value"})

    with pytest.raises(ValidationError, match="extra_forbidden"):
        handler.list_ledgers({"unknown_param": 123})


def test_schema_date_pattern_enforcement(handler):
    """Verify dates must strictly follow YYYY-MM-DD pattern."""
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        handler.get_party_ledger({
            "party": "Patel Textiles",
            "from_date": "01-04-2026",  # Invalid format
            "to_date": "2026-10-31",
        })


def test_execute_get_company_info(handler):
    """Test get_company_info MCP tool execution."""
    res = handler.get_company_info({})
    assert res["company_name"] == "Surat Textile Traders Pvt Ltd"
    assert res["currency_symbol"] == "₹"


def test_execute_list_ledgers_with_prefix_and_limit(handler):
    """Test list_ledgers with filtering and pagination limits."""
    # Prefix filter
    res = handler.list_ledgers({"name_prefix": "Patel"})
    assert res["returned_count"] == 1
    assert res["ledgers"][0]["name"] == "Patel Textiles"
    assert res["ledgers"][0]["closing_balance"] == "180000.00"

    # Limit filter
    res_limited = handler.list_ledgers({"limit": 2})
    assert res_limited["returned_count"] == 2
    assert res_limited["total_count"] == 10


def test_execute_get_party_ledger(handler):
    """Test get_party_ledger MCP tool execution and Decimal serialization."""
    res = handler.get_party_ledger({
        "party": "Patel Textiles",
        "from_date": "2026-04-01",
        "to_date": "2026-10-31",
    })
    assert res["ledger_name"] == "Patel Textiles"
    assert res["opening_balance"] == "150000.00"
    assert res["closing_balance"] == "180000.00"
    assert len(res["entries"]) == 2
    assert res["entries"][0]["amount"] == "100000.00"


def test_execute_get_receivables_ageing(handler):
    """Test get_receivables_ageing MCP tool execution."""
    res = handler.get_receivables_ageing({
        "as_on": "2026-10-31",
        "buckets": [30, 60, 90],
    })
    assert res["grand_total_receivables"] == "300000.00"
    assert res["parties_count"] == 2


def test_execute_get_stock_summary_filter(handler):
    """Test get_stock_summary with item/group filter."""
    res = handler.get_stock_summary({
        "as_on": "2026-10-31",
        "item_or_group": "Silk",
    })
    assert res["items_count"] == 1
    assert res["items"][0]["name"] == "Silk Chiffon 60g"
    assert res["total_valuation"] == "280000.00"
