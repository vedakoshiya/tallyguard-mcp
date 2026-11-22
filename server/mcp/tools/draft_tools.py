"""MCP Draft Write Tools Handler for TallyGuard MCP.

Implements FR-020 through FR-024 and Invariant INV-02:
Zero Direct Writes: Write operations strictly create draft proposals pending human approval.
Tools return draft_id, Dr/Cr lines, anomaly flags, and out-of-band approval URLs.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from bridge.tally_adapter.decimal_math import ensure_decimal, format_inr
from server.auth.tokens import TokenClaims
from server.auth.scopes import check_tool_permission
from server.auth.allowlist import LedgerAllowListValidator
from server.auth.rate_limiter import RateLimiter
from server.audit.hash_chain import AuditChainLogger
from server.drafts.lifecycle import DraftManager, Draft
from server.drafts.rules_engine import AnomalyRulesEngine
from server.mcp.schemas.draft_schemas import (
    DraftReceiptVoucherInput,
    DraftSalesVoucherInput,
    DraftPaymentVoucherInput,
    DraftJournalVoucherInput,
    GetDraftStatusInput,
    CancelDraftInput,
    DraftResponse,
    DraftSummaryLine,
)


class DraftToolsHandler:
    """Dispatches and executes MCP draft creation tools."""

    def __init__(
        self,
        draft_manager: DraftManager,
        rules_engine: AnomalyRulesEngine,
        audit_logger: AuditChainLogger,
        rate_limiter: RateLimiter,
        known_ledgers: Optional[Set[str]] = None,
        existing_vouchers: Optional[List[Dict[str, Any]]] = None,
    ):
        self.draft_manager = draft_manager
        self.rules_engine = rules_engine
        self.audit_logger = audit_logger
        self.rate_limiter = rate_limiter
        self.known_ledgers = known_ledgers or set()
        self.existing_vouchers = existing_vouchers or []

    def draft_receipt_voucher(
        self, claims: TokenClaims, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """FR-020: Prepare a receipt voucher draft."""
        check_tool_permission(claims, "draft_receipt_voucher")
        self.rate_limiter.check_and_increment_daily_drafts(claims.sub)

        params = DraftReceiptVoucherInput.model_validate(arguments)
        amount = ensure_decimal(params.amount)

        # Allow-list checks
        LedgerAllowListValidator.assert_ledger_permitted(params.party, None, claims.ledger_allowlist)
        LedgerAllowListValidator.assert_ledger_permitted(params.bank_cash_ledger, None, claims.ledger_allowlist)

        # Evaluate rules engine
        anomaly_report = self.rules_engine.evaluate_draft(
            party_name=params.party,
            total_amount=amount,
            voucher_date_str=params.date,
            known_ledgers=self.known_ledgers,
            existing_vouchers=self.existing_vouchers,
            user_allowlist=claims.ledger_allowlist,
        )

        # Construct normalized payload with Dr/Cr lines
        payload = {
            "voucher_type": "Receipt",
            "party": params.party,
            "bank_cash_ledger": params.bank_cash_ledger,
            "amount": f"{amount:.2f}",
            "date": params.date,
            "reference": params.reference or "",
            "narration": params.narration or "",
            "lines": [
                {"ledger": params.bank_cash_ledger, "amount": f"{amount:.2f}", "is_debit": True},
                {"ledger": params.party, "amount": f"{amount:.2f}", "is_debit": False},
            ],
        }

        # Store draft
        draft = self.draft_manager.create_draft(
            tenant_id=claims.tenant_id,
            user_id=claims.sub,
            client_id=claims.client_id,
            voucher_type="Receipt",
            payload=payload,
            flags=anomaly_report.flags,
            risk_level=anomaly_report.risk_level,
            requires_second_approver=anomaly_report.requires_second_approver,
        )

        # Log audit trail
        self.audit_logger.log(
            tenant_id=claims.tenant_id,
            tool="draft_receipt_voucher",
            raw_args=arguments,
            status="DRAFT_CREATED",
            actor_user=claims.sub,
            client_id=claims.client_id,
            result_summary={"draft_id": draft.id, "risk_level": draft.risk_level},
        )

        approval_url = self.draft_manager.get_approval_url(draft.id)
        summary_str = f"Receipt of {format_inr(amount)} from {params.party} on {params.date} to {params.bank_cash_ledger}"

        response = DraftResponse(
            draft_id=draft.id,
            status=draft.status,
            voucher_type=draft.voucher_type,
            summary=summary_str,
            lines=[
                DraftSummaryLine(ledger=params.bank_cash_ledger, dr=f"{amount:.2f}"),
                DraftSummaryLine(ledger=params.party, cr=f"{amount:.2f}"),
            ],
            flags=draft.flags,
            risk_level=draft.risk_level,
            approval_url=approval_url,
            expires_at=draft.expires_at,
        )
        return response.model_dump()

    def draft_sales_voucher(
        self, claims: TokenClaims, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """FR-021: Prepare a sales voucher draft."""
        check_tool_permission(claims, "draft_sales_voucher")
        self.rate_limiter.check_and_increment_daily_drafts(claims.sub)

        params = DraftSalesVoucherInput.model_validate(arguments)
        LedgerAllowListValidator.assert_ledger_permitted(params.party, None, claims.ledger_allowlist)

        total_amount = Decimal("0.00")
        items_payload = []
        for item in params.items:
            i_amt = ensure_decimal(item.amount)
            total_amount += i_amt
            items_payload.append({
                "item_name": item.item_name,
                "qty": item.qty,
                "rate": item.rate,
                "amount": f"{i_amt:.2f}",
                "tax_rate": item.tax_rate,
            })

        anomaly_report = self.rules_engine.evaluate_draft(
            party_name=params.party,
            total_amount=total_amount,
            voucher_date_str=params.date,
            known_ledgers=self.known_ledgers,
            existing_vouchers=self.existing_vouchers,
            user_allowlist=claims.ledger_allowlist,
        )

        payload = {
            "voucher_type": "Sales",
            "party": params.party,
            "sales_ledger": params.sales_ledger,
            "amount": f"{total_amount:.2f}",
            "date": params.date,
            "reference": params.reference or "",
            "narration": params.narration or "",
            "items": items_payload,
            "lines": [
                {"ledger": params.party, "amount": f"{total_amount:.2f}", "is_debit": True},
                {"ledger": params.sales_ledger, "amount": f"{total_amount:.2f}", "is_debit": False},
            ],
        }

        draft = self.draft_manager.create_draft(
            tenant_id=claims.tenant_id,
            user_id=claims.sub,
            client_id=claims.client_id,
            voucher_type="Sales",
            payload=payload,
            flags=anomaly_report.flags,
            risk_level=anomaly_report.risk_level,
            requires_second_approver=anomaly_report.requires_second_approver,
        )

        self.audit_logger.log(
            tenant_id=claims.tenant_id,
            tool="draft_sales_voucher",
            raw_args=arguments,
            status="DRAFT_CREATED",
            actor_user=claims.sub,
            client_id=claims.client_id,
            result_summary={"draft_id": draft.id, "total": f"{total_amount:.2f}"},
        )

        summary_str = f"Sales invoice of {format_inr(total_amount)} to {params.party} on {params.date}"
        approval_url = self.draft_manager.get_approval_url(draft.id)

        response = DraftResponse(
            draft_id=draft.id,
            status=draft.status,
            voucher_type=draft.voucher_type,
            summary=summary_str,
            lines=[
                DraftSummaryLine(ledger=params.party, dr=f"{total_amount:.2f}"),
                DraftSummaryLine(ledger=params.sales_ledger, cr=f"{total_amount:.2f}"),
            ],
            flags=draft.flags,
            risk_level=draft.risk_level,
            approval_url=approval_url,
            expires_at=draft.expires_at,
        )
        return response.model_dump()

    def draft_payment_voucher(
        self, claims: TokenClaims, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """FR-022: Prepare a payment voucher draft."""
        check_tool_permission(claims, "draft_payment_voucher")
        self.rate_limiter.check_and_increment_daily_drafts(claims.sub)

        params = DraftPaymentVoucherInput.model_validate(arguments)
        amount = ensure_decimal(params.amount)

        # Allow-list checks
        LedgerAllowListValidator.assert_ledger_permitted(params.party, None, claims.ledger_allowlist)
        LedgerAllowListValidator.assert_ledger_permitted(params.bank_cash_ledger, None, claims.ledger_allowlist)

        # Evaluate rules engine
        anomaly_report = self.rules_engine.evaluate_draft(
            party_name=params.party,
            total_amount=amount,
            voucher_date_str=params.date,
            known_ledgers=self.known_ledgers,
            existing_vouchers=self.existing_vouchers,
            user_allowlist=claims.ledger_allowlist,
        )

        # Construct normalized payload with Dr/Cr lines (Dr Party, Cr Bank/Cash)
        payload = {
            "voucher_type": "Payment",
            "party": params.party,
            "bank_cash_ledger": params.bank_cash_ledger,
            "amount": f"{amount:.2f}",
            "date": params.date,
            "reference": params.reference or "",
            "narration": params.narration or "",
            "lines": [
                {"ledger": params.party, "amount": f"{amount:.2f}", "is_debit": True},
                {"ledger": params.bank_cash_ledger, "amount": f"{amount:.2f}", "is_debit": False},
            ],
        }

        # Store draft
        draft = self.draft_manager.create_draft(
            tenant_id=claims.tenant_id,
            user_id=claims.sub,
            client_id=claims.client_id,
            voucher_type="Payment",
            payload=payload,
            flags=anomaly_report.flags,
            risk_level=anomaly_report.risk_level,
            requires_second_approver=anomaly_report.requires_second_approver,
        )

        self.audit_logger.log(
            tenant_id=claims.tenant_id,
            tool="draft_payment_voucher",
            raw_args=arguments,
            status="DRAFT_CREATED",
            actor_user=claims.sub,
            client_id=claims.client_id,
            result_summary={"draft_id": draft.id, "risk_level": draft.risk_level},
        )

        approval_url = self.draft_manager.get_approval_url(draft.id)
        summary_str = f"Payment of {format_inr(amount)} to {params.party} on {params.date} from {params.bank_cash_ledger}"

        response = DraftResponse(
            draft_id=draft.id,
            status=draft.status,
            voucher_type=draft.voucher_type,
            summary=summary_str,
            lines=[
                DraftSummaryLine(ledger=params.party, dr=f"{amount:.2f}"),
                DraftSummaryLine(ledger=params.bank_cash_ledger, cr=f"{amount:.2f}"),
            ],
            flags=draft.flags,
            risk_level=draft.risk_level,
            approval_url=approval_url,
            expires_at=draft.expires_at,
        )
        return response.model_dump()

    def draft_journal_voucher(
        self, claims: TokenClaims, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """FR-022: Prepare a journal voucher draft with strict Dr == Cr balancing."""
        check_tool_permission(claims, "draft_journal_voucher")
        self.rate_limiter.check_and_increment_daily_drafts(claims.sub)

        params = DraftJournalVoucherInput.model_validate(arguments)

        # Verify double-entry balance and allow-lists
        total_dr = Decimal("0.00")
        total_cr = Decimal("0.00")
        lines_payload = []
        summary_lines = []

        for line in params.lines:
            LedgerAllowListValidator.assert_ledger_permitted(line.ledger, None, claims.ledger_allowlist)
            l_amt = ensure_decimal(line.amount)
            if line.is_debit:
                total_dr += l_amt
                summary_lines.append(DraftSummaryLine(ledger=line.ledger, dr=f"{l_amt:.2f}"))
            else:
                total_cr += l_amt
                summary_lines.append(DraftSummaryLine(ledger=line.ledger, cr=f"{l_amt:.2f}"))

            lines_payload.append({
                "ledger": line.ledger,
                "amount": f"{l_amt:.2f}",
                "is_debit": line.is_debit,
            })

        if total_dr != total_cr:
            raise ValueError(
                f"VALIDATION_FAILED: Journal voucher is unbalanced. Total Debits (₹{total_dr:.2f}) "
                f"must equal Total Credits (₹{total_cr:.2f})."
            )

        # Primary ledger for anomaly evaluation is first debit ledger or first ledger
        primary_party = params.lines[0].ledger
        anomaly_report = self.rules_engine.evaluate_draft(
            party_name=primary_party,
            total_amount=total_dr,
            voucher_date_str=params.date,
            known_ledgers=self.known_ledgers,
            existing_vouchers=self.existing_vouchers,
            user_allowlist=claims.ledger_allowlist,
        )

        payload = {
            "voucher_type": "Journal",
            "date": params.date,
            "narration": params.narration or "",
            "amount": f"{total_dr:.2f}",
            "lines": lines_payload,
        }

        draft = self.draft_manager.create_draft(
            tenant_id=claims.tenant_id,
            user_id=claims.sub,
            client_id=claims.client_id,
            voucher_type="Journal",
            payload=payload,
            flags=anomaly_report.flags,
            risk_level=anomaly_report.risk_level,
            requires_second_approver=anomaly_report.requires_second_approver,
        )

        self.audit_logger.log(
            tenant_id=claims.tenant_id,
            tool="draft_journal_voucher",
            raw_args=arguments,
            status="DRAFT_CREATED",
            actor_user=claims.sub,
            client_id=claims.client_id,
            result_summary={"draft_id": draft.id, "total": f"{total_dr:.2f}"},
        )

        approval_url = self.draft_manager.get_approval_url(draft.id)
        summary_str = f"Journal voucher of {format_inr(total_dr)} on {params.date} with {len(params.lines)} balanced lines"

        response = DraftResponse(
            draft_id=draft.id,
            status=draft.status,
            voucher_type=draft.voucher_type,
            summary=summary_str,
            lines=summary_lines,
            flags=draft.flags,
            risk_level=draft.risk_level,
            approval_url=approval_url,
            expires_at=draft.expires_at,
        )
        return response.model_dump()

    def get_draft_status(
        self, claims: TokenClaims, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """FR-023: Query draft status."""
        check_tool_permission(claims, "get_draft_status")
        params = GetDraftStatusInput.model_validate(arguments)

        draft = self.draft_manager.get_draft(params.draft_id)
        if not draft or draft.tenant_id != claims.tenant_id:
            return {"error": "DRAFT_NOT_FOUND", "message": f"Draft '{params.draft_id}' not found."}

        return draft.to_dict()

    def cancel_draft(
        self, claims: TokenClaims, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """FR-023: Cancel an own draft."""
        check_tool_permission(claims, "cancel_draft")
        params = CancelDraftInput.model_validate(arguments)

        cancelled_draft = self.draft_manager.cancel_draft(params.draft_id, claims.sub)
        self.audit_logger.log(
            tenant_id=claims.tenant_id,
            tool="cancel_draft",
            raw_args=arguments,
            status="DRAFT_CANCELLED",
            actor_user=claims.sub,
            client_id=claims.client_id,
        )
        return {"draft_id": cancelled_draft.id, "status": cancelled_draft.status}
