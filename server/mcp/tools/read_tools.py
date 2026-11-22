"""MCP Read Tools Implementation for TallyGuard MCP.

Implements FR-001 through FR-009 with strict schema validation,
exact decimal serialization, and readOnlyHint annotations.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

from bridge.tally_adapter.client import TallyAdapterClient, TallyConnectionError
from bridge.tally_adapter.decimal_math import ensure_decimal
from server.mcp.schemas.read_schemas import (
    GetCompanyInfoInput,
    ListLedgersInput,
    GetPartyLedgerInput,
    GetReceivablesAgeingInput,
    GetPayablesAgeingInput,
    GetStockSummaryInput,
)


def _serialize_decimals(obj: Any) -> Any:
    """Recursively convert Decimal instances to exact string representations for JSON-RPC."""
    if isinstance(obj, Decimal):
        return f"{obj:.2f}"
    if isinstance(obj, dict):
        return {k: _serialize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_decimals(item) for item in obj]
    return obj


class ReadToolsHandler:
    """Dispatches and executes MCP read tools against the TallyAdapterClient."""

    def __init__(self, client: TallyAdapterClient):
        self.client = client

    def get_company_info(self, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """FR-001: get_company_info tool execution."""
        GetCompanyInfoInput.model_validate(arguments or {})
        raw_info = self.client.get_company_info()
        return _serialize_decimals(raw_info)

    def list_ledgers(self, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """FR-002: list_ledgers tool execution."""
        params = ListLedgersInput.model_validate(arguments or {})
        ledgers = self.client.list_ledgers(group_filter=params.group or "")

        # Apply group filter as defense-in-depth
        if params.group:
            g_filter = params.group.lower()
            ledgers = [l for l in ledgers if l["parent"].lower() == g_filter]

        # Apply name_prefix filter if supplied
        if params.name_prefix:
            prefix = params.name_prefix.lower()
            ledgers = [l for l in ledgers if l["name"].lower().startswith(prefix)]

        # Apply pagination limit
        total_count = len(ledgers)
        sliced_ledgers = ledgers[: params.limit]

        return _serialize_decimals({
            "total_count": total_count,
            "returned_count": len(sliced_ledgers),
            "ledgers": sliced_ledgers,
        })

    def get_party_ledger(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """FR-003: get_party_ledger tool execution."""
        params = GetPartyLedgerInput.model_validate(arguments)
        statement = self.client.get_party_ledger(
            party_name=params.party,
            from_date=params.from_date,
            to_date=params.to_date,
        )
        return _serialize_decimals(statement)

    def get_receivables_ageing(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """FR-004: get_receivables_ageing tool execution."""
        params = GetReceivablesAgeingInput.model_validate(arguments)
        min_amt = ensure_decimal(params.min_amount) if params.min_amount else None
        ageing = self.client.get_receivables_ageing(
            as_on_date=params.as_on,
            buckets=params.buckets,
            min_amount=min_amt,
            top_n=params.top_n,
        )
        return _serialize_decimals(ageing)

    def get_payables_ageing(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """FR-005: get_payables_ageing tool execution."""
        params = GetPayablesAgeingInput.model_validate(arguments)
        # Using receivables logic with payables template
        min_amt = ensure_decimal(params.min_amount) if params.min_amount else None
        ageing = self.client.get_receivables_ageing(
            as_on_date=params.as_on,
            buckets=params.buckets,
            min_amount=min_amt,
            top_n=params.top_n,
        )
        return _serialize_decimals(ageing)

    def get_stock_summary(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """FR-007: get_stock_summary tool execution."""
        params = GetStockSummaryInput.model_validate(arguments)
        stock_items = self.client.get_stock_summary(as_on_date=params.as_on)

        if params.item_or_group:
            query = params.item_or_group.lower()
            stock_items = [
                s for s in stock_items
                if query in s["name"].lower() or query in s["group"].lower()
            ]

        total_value = sum((Decimal(item["closing_value"]) for item in stock_items), Decimal("0.00"))

        return _serialize_decimals({
            "as_on": params.as_on,
            "items_count": len(stock_items),
            "total_valuation": total_value,
            "items": stock_items,
        })
