"""Pydantic v2 Schemas for TallyGuard MCP Draft Write Tools.

Implements FR-020 to FR-024, enforcing:
1. Strict schema validation with extra="forbid" (FR-082).
2. Decimal currency patterns and date format verification.
3. Structured output response returning draft_id, Dr/Cr lines, anomaly flags, and approval_url.
4. Guarantee: Tools output draft proposals only; they never write directly to Tally.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictBaseModel(BaseModel):
    """Base model forbidding unknown extra properties."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DraftVoucherLineInput(StrictBaseModel):
    """Individual debit/credit line for journal drafts."""

    ledger: str = Field(..., min_length=1, max_length=200, description="Ledger account name.")
    amount: str = Field(
        ...,
        pattern=r"^[0-9]+(\.[0-9]{1,2})?$",
        description="Amount in decimal currency format (e.g. '25000.00').",
    )
    is_debit: bool = Field(..., description="True if Debit (Dr), False if Credit (Cr).")


class DraftReceiptVoucherInput(StrictBaseModel):
    """Input for draft_receipt_voucher tool (FR-020)."""

    party: str = Field(..., min_length=1, max_length=200, description="Debtor/Party name paying funds.")
    amount: str = Field(
        ...,
        pattern=r"^[0-9]+(\.[0-9]{1,2})?$",
        description="Monetary amount received (e.g. '20000.00').",
    )
    date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Receipt date in YYYY-MM-DD format.",
    )
    bank_cash_ledger: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Receiving bank or cash ledger (e.g. 'HDFC Bank', 'Cash in Hand').",
    )
    reference: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Invoice reference, NEFT ref, or cheque number.",
    )
    narration: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Voucher narration remarks.",
    )


class SalesItemInput(StrictBaseModel):
    """Line item in sales voucher draft."""

    item_name: str = Field(..., min_length=1, max_length=200, description="Stock item name.")
    qty: str = Field(..., pattern=r"^[0-9]+(\.[0-9]{1,4})?$", description="Quantity sold.")
    rate: str = Field(..., pattern=r"^[0-9]+(\.[0-9]{1,2})?$", description="Rate per unit.")
    amount: str = Field(..., pattern=r"^[0-9]+(\.[0-9]{1,2})?$", description="Line item amount.")
    tax_rate: Optional[str] = Field(default="5.0", description="GST tax rate percentage.")


class DraftSalesVoucherInput(StrictBaseModel):
    """Input for draft_sales_voucher tool (FR-021)."""

    party: str = Field(..., min_length=1, max_length=200, description="Customer / Buyer name.")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Sales invoice date (YYYY-MM-DD).")
    items: List[SalesItemInput] = Field(..., min_length=1, description="List of invoiced items.")
    sales_ledger: str = Field(default="Sales Account", description="Sales ledger account.")
    reference: Optional[str] = Field(default=None, description="Buyer PO number or delivery challan.")
    narration: Optional[str] = Field(default=None, max_length=1000, description="Voucher narration.")


class DraftPaymentVoucherInput(StrictBaseModel):
    """Input for draft_payment_voucher tool (FR-022)."""

    party: str = Field(..., min_length=1, max_length=200, description="Creditor/Vendor name paid.")
    amount: str = Field(..., pattern=r"^[0-9]+(\.[0-9]{1,2})?$", description="Amount paid.")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Payment date (YYYY-MM-DD).")
    bank_cash_ledger: str = Field(..., description="Paying bank or cash account.")
    reference: Optional[str] = Field(default=None, description="Payment ref or cheque number.")
    narration: Optional[str] = Field(default=None, max_length=1000, description="Narration.")


class DraftJournalVoucherInput(StrictBaseModel):
    """Input for draft_journal_voucher tool (FR-022)."""

    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Journal date (YYYY-MM-DD).")
    lines: List[DraftVoucherLineInput] = Field(..., min_length=2, description="At least two balanced lines.")
    narration: Optional[str] = Field(default=None, max_length=1000, description="Narration.")


class GetDraftStatusInput(StrictBaseModel):
    """Input for get_draft_status tool (FR-023)."""

    draft_id: str = Field(..., min_length=1, description="Unique Draft ID.")


class CancelDraftInput(StrictBaseModel):
    """Input for cancel_draft tool (FR-023)."""

    draft_id: str = Field(..., min_length=1, description="Unique Draft ID to cancel.")


class ApprovalDecisionInput(StrictBaseModel):
    """Input for submitting out-of-band human approval."""

    decision: str = Field(..., pattern=r"^(approve|reject)$", description="'approve' or 'reject'.")
    channel: str = Field(default="web", description="Approval channel (e.g. web, mobile, whatsapp).")
    note: Optional[str] = Field(default=None, max_length=500, description="Approver's remarks.")


class DraftSummaryLine(BaseModel):
    """Dr/Cr representation line in draft response."""

    ledger: str
    dr: Optional[str] = None
    cr: Optional[str] = None


class DraftResponse(BaseModel):
    """Standard draft tool output response (FR-024)."""

    draft_id: str
    status: str
    voucher_type: str
    summary: str
    lines: List[DraftSummaryLine]
    flags: List[str]
    risk_level: str
    approval_url: str
    expires_at: str
    note: str = "Not posted. A human approver must approve in the approval page."
