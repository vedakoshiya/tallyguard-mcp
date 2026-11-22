"""Draft Lifecycle & Storage Engine for TallyGuard MCP.

Implements FR-060, FR-064, and Invariants INV-02 & INV-04.
Manages the formal draft state machine:
  created -> pending_approval -> approved | rejected | expired -> posted | failed | cancelled

Enforces:
1. Canonical payload hashing at creation.
2. 48-hour configurable expiration.
3. User scoping on draft cancellations (users can only cancel their own drafts).
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from server.auth.scopes import ScopeDeniedError
from server.drafts.hashing import compute_payload_hash


class DraftStateError(Exception):
    """Raised when an invalid state transition is attempted on a draft."""


@dataclass
class Draft:
    """Represents a proposed voucher stored outside Tally pending human approval."""

    id: str
    tenant_id: str
    created_by: str
    client_id: str
    voucher_type: str
    payload: dict[str, Any]
    payload_hash: str
    flags: list[str]
    risk_level: str
    requires_second_approver: bool
    status: str  # pending_approval, pending_second_approval, approved, rejected, expired, posted, failed, cancelled
    idempotency_key: str
    expires_at: str
    created_at: str
    tally_voucher_no: str | None = None
    approver_ids: list[str] = field(default_factory=list)
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DraftManager:
    """Manages draft creation, retrieval, cancellation, and expiration."""

    def __init__(self, default_expiry_hours: int = 48, base_approval_url: str = "https://tallyguard.local/approve/"):
        self.default_expiry_hours = default_expiry_hours
        self.base_approval_url = base_approval_url.rstrip("/") + "/"
        self._drafts: dict[str, Draft] = {}

    def create_draft(
        self,
        tenant_id: str,
        user_id: str,
        client_id: str,
        voucher_type: str,
        payload: dict[str, Any],
        flags: list[str],
        risk_level: str,
        requires_second_approver: bool = False,
        expiry_hours: int | None = None,
    ) -> Draft:
        """Create a new draft in pending_approval state."""
        draft_id = f"d_{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        exp_hours = expiry_hours or self.default_expiry_hours
        expires_at = (now + timedelta(hours=exp_hours)).isoformat()
        created_at = now.isoformat()

        payload_hash = compute_payload_hash(payload)
        idempotency_key = f"tallyguard_{draft_id}_{uuid.uuid4().hex[:8]}"

        draft = Draft(
            id=draft_id,
            tenant_id=tenant_id,
            created_by=user_id,
            client_id=client_id,
            voucher_type=voucher_type,
            payload=payload,
            payload_hash=payload_hash,
            flags=flags,
            risk_level=risk_level,
            requires_second_approver=requires_second_approver,
            status="pending_approval",
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            created_at=created_at,
        )

        self._drafts[draft_id] = draft
        return draft

    def get_draft(self, draft_id: str) -> Draft | None:
        """Fetch draft by ID, updating expiration if passed."""
        draft = self._drafts.get(draft_id)
        if not draft:
            return None

        # Check expiration
        now_iso = datetime.now(UTC).isoformat()
        if draft.status in ("pending_approval", "pending_second_approval") and draft.expires_at < now_iso:
            draft.status = "expired"

        return draft

    def cancel_draft(self, draft_id: str, requesting_user_id: str) -> Draft:
        """Cancel a pending draft. Only the creator can cancel their draft."""
        draft = self.get_draft(draft_id)
        if not draft:
            raise DraftStateError(f"Draft '{draft_id}' not found.")

        if draft.created_by != requesting_user_id:
            raise ScopeDeniedError(
                f"SCOPE_DENIED: User '{requesting_user_id}' cannot cancel draft '{draft_id}' "
                f"created by '{draft.created_by}'. Users can only cancel their own drafts.",
                required_scope="own_draft",
                granted_scopes=[],
            )

        if draft.status not in ("pending_approval", "pending_second_approval"):
            raise DraftStateError(
                f"Cannot cancel draft in '{draft.status}' state. Only pending drafts can be cancelled."
            )

        draft.status = "cancelled"
        return draft

    def get_approval_url(self, draft_id: str) -> str:
        """Construct out-of-band approval URL."""
        return f"{self.base_approval_url}{draft_id}"
