"""Pydantic v2 Schemas for TallyGuard MCP Read Tools.

Enforces strict type validation, parameter pattern checks, and rejects unknown fields
(extra="forbid") per FR-041 and FR-082.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    """Base model forbidding undeclared extra properties."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class GetCompanyInfoInput(StrictBaseModel):
    """Input for get_company_info tool. Side-effect free."""
    pass


class ListLedgersInput(StrictBaseModel):
    """Input for list_ledgers tool."""

    group: Optional[str] = Field(
        default=None,
        description="Filter by parent group name (e.g. 'Sundry Debtors', 'Bank Accounts').",
    )
    name_prefix: Optional[str] = Field(
        default=None,
        description="Filter ledgers starting with a given prefix.",
    )
    cursor: Optional[str] = Field(
        default=None,
        description="Opaque cursor for pagination.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of records to return.",
    )


class GetPartyLedgerInput(StrictBaseModel):
    """Input for get_party_ledger tool."""

    party: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Exact party/ledger name as recorded in Tally.",
    )
    from_date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Start date in YYYY-MM-DD format.",
    )
    to_date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="End date in YYYY-MM-DD format.",
    )


class GetReceivablesAgeingInput(StrictBaseModel):
    """Input for get_receivables_ageing tool."""

    as_on: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Date on which ageing is calculated (YYYY-MM-DD).",
    )
    buckets: List[int] = Field(
        default=[30, 60, 90],
        description="Age bucket thresholds in days (e.g. [30, 60, 90] yields 0-30, 31-60, 61-90, 90+).",
    )
    min_amount: Optional[str] = Field(
        default=None,
        pattern=r"^[0-9]+(\.[0-9]{1,2})?$",
        description="Optional minimum bill amount filter (e.g. '1000.00').",
    )
    top_n: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Top N parties with highest outstanding balances.",
    )


class GetPayablesAgeingInput(StrictBaseModel):
    """Input for get_payables_ageing tool."""

    as_on: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Date on which ageing is calculated (YYYY-MM-DD).",
    )
    buckets: List[int] = Field(
        default=[30, 60, 90],
        description="Age bucket thresholds in days.",
    )
    min_amount: Optional[str] = Field(
        default=None,
        pattern=r"^[0-9]+(\.[0-9]{1,2})?$",
        description="Optional minimum bill amount filter.",
    )
    top_n: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Top N creditor parties with highest outstanding balances.",
    )


class SearchVouchersInput(StrictBaseModel):
    """Input for search_vouchers tool."""

    voucher_type: Optional[str] = Field(
        default=None,
        description="Voucher type filter (Sales, Receipt, Payment, Purchase, Journal).",
    )
    party: Optional[str] = Field(
        default=None,
        description="Filter by party name.",
    )
    min_amount: Optional[str] = Field(
        default=None,
        pattern=r"^[0-9]+(\.[0-9]{1,2})?$",
        description="Minimum voucher amount.",
    )
    max_amount: Optional[str] = Field(
        default=None,
        pattern=r"^[0-9]+(\.[0-9]{1,2})?$",
        description="Maximum voucher amount.",
    )
    from_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Voucher date from (YYYY-MM-DD).",
    )
    to_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Voucher date to (YYYY-MM-DD).",
    )
    narration_query: Optional[str] = Field(
        default=None,
        description="Substring search within voucher narration.",
    )
    cursor: Optional[str] = Field(
        default=None,
        description="Opaque pagination cursor.",
    )
    limit: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Maximum number of vouchers to return.",
    )


class GetStockSummaryInput(StrictBaseModel):
    """Input for get_stock_summary tool."""

    as_on: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Stock valuation date (YYYY-MM-DD).",
    )
    item_or_group: Optional[str] = Field(
        default=None,
        description="Filter by stock item name or stock group.",
    )


class GetGstSummaryInput(StrictBaseModel):
    """Input for get_gst_summary tool."""

    period_from: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Tax period start date (YYYY-MM-DD).",
    )
    period_to: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Tax period end date (YYYY-MM-DD).",
    )


class GetFinancialStatementsInput(StrictBaseModel):
    """Input for financial statements tools (trial balance, P&L, balance sheet)."""

    statement_type: str = Field(
        ...,
        pattern=r"^(trial_balance|profit_and_loss|balance_sheet)$",
        description="Type of financial statement.",
    )
    period_from: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Period start date (YYYY-MM-DD).",
    )
    period_to: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Period end date (YYYY-MM-DD).",
    )
