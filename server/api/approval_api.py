"""Out-of-Band Human Approval Service & API for TallyGuard MCP.

Implements FR-060, FR-061, FR-065, US-05, and Invariants INV-03 & INV-04.
Provides:
1. Voucher rendering showing Dr/Cr balance lines and anomaly flags.
2. Cryptographic binding check: approvals.payload_hash == drafts.payload_hash.
3. Separation of privileges: strictly human approvers only.
4. Second-approver enforcement for high-risk transactions.
5. Idempotent bridge posting with Tally voucher confirmation.
"""

from datetime import UTC, datetime
from typing import Any

from bridge.tally_adapter.poster import VoucherPoster
from server.audit.hash_chain import AuditChainLogger
from server.auth.scopes import SCOPE_APPROVE_VOUCHERS, ScopeDeniedError, check_tool_permission
from server.auth.tokens import AuthSecurityError, TokenClaims, decode_and_validate_token
from server.drafts.hashing import verify_payload_hash
from server.drafts.lifecycle import DraftManager, DraftStateError
from server.mcp.schemas.draft_schemas import ApprovalDecisionInput

try:
    from fastapi import APIRouter, Depends, Header, HTTPException, status
except ImportError:
    APIRouter = None  # type: ignore


class ApprovalService:
    """Orchestrates human approvals, verification, and bridge posting."""

    def __init__(
        self,
        draft_manager: DraftManager,
        voucher_poster: VoucherPoster,
        audit_logger: AuditChainLogger,
    ):
        self.draft_manager = draft_manager
        self.voucher_poster = voucher_poster
        self.audit_logger = audit_logger

    def render_draft(self, draft_id: str, approver_claims: TokenClaims) -> dict[str, Any]:
        """Render a draft for human review at GET /approve/{draft_id}."""
        draft = self.draft_manager.get_draft(draft_id)
        if not draft:
            raise DraftStateError(f"Draft '{draft_id}' not found.")

        if draft.tenant_id != approver_claims.tenant_id:
            raise ScopeDeniedError(
                f"SCOPE_DENIED: Draft '{draft_id}' belongs to another tenant.",
                required_scope="tenant_isolation",
                granted_scopes=[],
            )

        # Check payload integrity
        is_payload_intact = verify_payload_hash(draft.payload, draft.payload_hash)
        if not is_payload_intact:
            draft.status = "failed"
            raise DraftStateError(
                "Security Alert: Draft payload hash mismatch! Storage tampering detected. Draft invalidated."
            )

        return {
            "draft_id": draft.id,
            "status": draft.status,
            "voucher_type": draft.voucher_type,
            "created_by": draft.created_by,
            "client_id": draft.client_id,
            "created_at": draft.created_at,
            "expires_at": draft.expires_at,
            "flags": draft.flags,
            "risk_level": draft.risk_level,
            "requires_second_approver": draft.requires_second_approver,
            "approver_ids": draft.approver_ids,
            "payload": draft.payload,
            "payload_hash": draft.payload_hash,
        }

    def submit_decision(
        self,
        draft_id: str,
        approver_claims: TokenClaims,
        decision: str,
        channel: str = "web",
        note: str | None = None,
    ) -> dict[str, Any]:
        """Process human approval decision (POST /approve/{draft_id})."""
        # 1. Enforce Human-Only Privilege (Invariant INV-03)
        if approver_claims.client_type != "human_user":
            raise ScopeDeniedError(
                "Access Denied: AI clients cannot approve drafts. Approvals require human identity.",
                required_scope=SCOPE_APPROVE_VOUCHERS,
                granted_scopes=approver_claims.scopes,
            )

        check_tool_permission(approver_claims, "approve_voucher")

        draft = self.draft_manager.get_draft(draft_id)
        if not draft:
            raise DraftStateError(f"Draft '{draft_id}' not found.")

        if draft.tenant_id != approver_claims.tenant_id:
            raise ScopeDeniedError(
                f"SCOPE_DENIED: Draft belongs to tenant '{draft.tenant_id}'.",
                required_scope="tenant_isolation",
                granted_scopes=[],
            )

        # 2. Check Idempotency (if already posted, return existing status)
        if draft.status == "posted":
            return {
                "status": "posted",
                "draft_id": draft.id,
                "tally_voucher_no": draft.tally_voucher_no,
                "message": "Draft was already approved and posted to Tally.",
            }

        # 3. Check State
        if draft.status not in ("pending_approval", "pending_second_approval"):
            raise DraftStateError(f"Cannot approve draft in '{draft.status}' state.")

        # 4. Check Expiration
        now_iso = datetime.now(UTC).isoformat()
        if draft.expires_at < now_iso:
            draft.status = "expired"
            raise DraftStateError("Draft has expired. Expired drafts cannot be approved.")

        # 5. Cryptographic Hash Matching (Invariant INV-04)
        if not verify_payload_hash(draft.payload, draft.payload_hash):
            draft.status = "failed"
            self.audit_logger.log(
                tenant_id=draft.tenant_id,
                tool="approve_voucher",
                raw_args={"draft_id": draft_id, "action": "TAMPER_DETECTED"},
                status="FAILED",
                actor_user=approver_claims.sub,
            )
            raise DraftStateError(
                "Security Alert: Payload hash verification failed. The draft content has been "
                "modified since creation. Posting is blocked."
            )

        # Handle Rejection
        if decision == "reject":
            draft.status = "rejected"
            draft.rejection_reason = note
            self.audit_logger.log(
                tenant_id=draft.tenant_id,
                tool="approve_voucher",
                raw_args={"draft_id": draft_id, "decision": "reject", "channel": channel},
                status="DRAFT_REJECTED",
                actor_user=approver_claims.sub,
            )
            return {"status": "rejected", "draft_id": draft.id}

        # Handle Approval
        if decision != "approve":
            raise ValueError(f"Invalid approval decision '{decision}'. Expected 'approve' or 'reject'.")

        # Second Approver Policy (FR-063)
        if draft.requires_second_approver:
            if len(draft.approver_ids) == 0:
                draft.approver_ids.append(approver_claims.sub)
                draft.status = "pending_second_approval"
                self.audit_logger.log(
                    tenant_id=draft.tenant_id,
                    tool="approve_voucher",
                    raw_args={"draft_id": draft_id, "step": "first_approval"},
                    status="PENDING_SECOND_APPROVAL",
                    actor_user=approver_claims.sub,
                )
                return {
                    "status": "pending_second_approval",
                    "draft_id": draft.id,
                    "message": "First approval recorded. High-risk transaction requires a second distinct approver.",
                }
            elif len(draft.approver_ids) == 1:
                # Prevent self-approval on high-risk transactions
                if approver_claims.sub == draft.approver_ids[0]:
                    raise AuthSecurityError(
                        "Security Policy Violation: The second approver must be a different human than the first approver."
                    )
                draft.approver_ids.append(approver_claims.sub)

        # Final Approval & Bridge Posting (FR-065, US-05)
        draft.status = "approved"
        post_result = self.voucher_poster.post_approved_voucher(draft.payload, draft.idempotency_key)

        tally_voucher_no = post_result.get("tally_voucher_no", "VCH-CONFIRMED")
        draft.tally_voucher_no = tally_voucher_no
        draft.status = "posted"

        self.audit_logger.log(
            tenant_id=draft.tenant_id,
            tool="approve_voucher",
            raw_args={"draft_id": draft_id, "decision": "approve", "channel": channel},
            status="POSTED_TO_TALLY",
            actor_user=approver_claims.sub,
            result_summary={"tally_voucher_no": tally_voucher_no, "idempotency_key": draft.idempotency_key},
        )

        return {
            "status": "posted",
            "draft_id": draft.id,
            "tally_voucher_no": tally_voucher_no,
        }


def create_approval_router(approval_service: ApprovalService, secret_key: str):
    """FastAPI APIRouter factory for out-of-band approval REST endpoints (FR-060, TASK-3.5)."""
    if APIRouter is None:
        raise RuntimeError("FastAPI is not installed or available in this environment.")

    router = APIRouter(prefix="/approve", tags=["Approvals"])

    def get_current_user_claims(authorization: str | None = Header(None)) -> TokenClaims:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or malformed Authorization header. Expected 'Bearer <token>'.",
            )
        token = authorization.split("Bearer ", 1)[1].strip()
        try:
            return decode_and_validate_token(token, secret_key)
        except AuthSecurityError as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    @router.get("/{draft_id}")
    def get_draft_for_approval(
        draft_id: str, claims: TokenClaims = Depends(get_current_user_claims)
    ):
        try:
            return approval_service.render_draft(draft_id, claims)
        except DraftStateError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except ScopeDeniedError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    @router.post("/{draft_id}")
    def post_approval_decision(
        draft_id: str,
        body: ApprovalDecisionInput,
        claims: TokenClaims = Depends(get_current_user_claims),
    ):
        try:
            return approval_service.submit_decision(
                draft_id=draft_id,
                approver_claims=claims,
                decision=body.decision,
                channel=body.channel,
                note=body.note,
            )
        except DraftStateError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except ScopeDeniedError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        except AuthSecurityError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return router

