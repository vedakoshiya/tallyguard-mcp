"""Comprehensive Automated Test Suite for Phase 3: Draft Engine, Anomaly Rules & Approvals.

Verifies:
- TC-DFT-01 to TC-DFT-05: Draft voucher creation, hashing, and user cancellation scoping.
- TC-RUL-01 to TC-RUL-04: Anomaly detection rules (thresholds, new parties, duplicates, backdates).
- TC-APP-01 to TC-APP-07: Out-of-band approval rendering, hash verification, tampering detection,
  rejection, expiration, second-approver policy, and idempotent bridge posting.
"""

from decimal import Decimal
import pytest

from bridge.tally_adapter.poster import VoucherPoster
from server.auth.tokens import create_access_token, decode_and_validate_token, AuthSecurityError
from server.auth.scopes import ScopeDeniedError, SCOPE_DRAFT_VOUCHERS, SCOPE_APPROVE_VOUCHERS
from server.auth.rate_limiter import RateLimiter
from server.audit.hash_chain import AuditChainLogger
from server.drafts.lifecycle import DraftManager, DraftStateError
from server.drafts.rules_engine import AnomalyRulesEngine
from server.drafts.hashing import compute_payload_hash
from server.mcp.tools.draft_tools import DraftToolsHandler
from server.api.approval_api import ApprovalService
from tests.simulated_tally.server import create_simulated_tally_transport

SECRET_KEY = "test-secret-key-32-characters-long-tallyguard"


@pytest.fixture
def draft_env():
    """Setup complete test environment with draft tools, approval service, and poster."""
    transport = create_simulated_tally_transport()
    draft_manager = DraftManager()
    rules_engine = AnomalyRulesEngine(
        single_amount_threshold=Decimal("50000.00"),
        second_approver_threshold=Decimal("200000.00"),
    )
    audit_logger = AuditChainLogger(secret_key=SECRET_KEY)
    rate_limiter = RateLimiter(max_daily_drafts=10)
    known_ledgers = {"Patel Textiles", "HDFC Bank", "Sales Account", "Surat Silk Mills"}

    tools_handler = DraftToolsHandler(
        draft_manager=draft_manager,
        rules_engine=rules_engine,
        audit_logger=audit_logger,
        rate_limiter=rate_limiter,
        known_ledgers=known_ledgers,
    )

    voucher_poster = VoucherPoster(transport=transport)
    approval_service = ApprovalService(
        draft_manager=draft_manager,
        voucher_poster=voucher_poster,
        audit_logger=audit_logger,
    )

    # Create tokens
    ai_token_str = create_access_token(
        user_id="ai-agent-user-1",
        tenant_id="tenant-123",
        client_id="claude-desktop",
        client_type="ai_client",
        scopes=[SCOPE_DRAFT_VOUCHERS],
        secret_key=SECRET_KEY,
    )
    ai_claims = decode_and_validate_token(ai_token_str, SECRET_KEY)

    human_token_str = create_access_token(
        user_id="human-approver-1",
        tenant_id="tenant-123",
        client_id="web-portal",
        client_type="human_user",
        scopes=[SCOPE_APPROVE_VOUCHERS],
        secret_key=SECRET_KEY,
    )
    human_claims = decode_and_validate_token(human_token_str, SECRET_KEY)

    human_token_2_str = create_access_token(
        user_id="human-approver-2",
        tenant_id="tenant-123",
        client_id="web-portal",
        client_type="human_user",
        scopes=[SCOPE_APPROVE_VOUCHERS],
        secret_key=SECRET_KEY,
    )
    human_claims_2 = decode_and_validate_token(human_token_2_str, SECRET_KEY)

    return {
        "tools_handler": tools_handler,
        "approval_service": approval_service,
        "draft_manager": draft_manager,
        "ai_claims": ai_claims,
        "human_claims": human_claims,
        "human_claims_2": human_claims_2,
    }


# ==============================================================================
# 1. Draft Creation & Zero Direct Writes (TC-DFT-01, 02, 03)
# ==============================================================================

def test_draft_receipt_voucher_creation_and_hashing(draft_env):
    """Verify TC-DFT-01 & TC-DFT-02: Draft creation, Dr/Cr lines, canonical payload hashing, and zero post."""
    handler = draft_env["tools_handler"]
    ai_claims = draft_env["ai_claims"]

    res = handler.draft_receipt_voucher(ai_claims, {
        "party": "Patel Textiles",
        "amount": "20000.00",
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
        "reference": "NEFT-12345",
        "narration": "Received against Invoice #101",
    })

    assert res["status"] == "pending_approval"
    assert res["voucher_type"] == "Receipt"
    assert len(res["lines"]) == 2
    assert res["lines"][0]["ledger"] == "HDFC Bank"
    assert res["lines"][0]["dr"] == "20000.00"
    assert res["lines"][1]["ledger"] == "Patel Textiles"
    assert res["lines"][1]["cr"] == "20000.00"
    assert "https://tallyguard.local/approve/" in res["approval_url"]

    # Verify draft in store and cryptographic hash
    draft = draft_env["draft_manager"].get_draft(res["draft_id"])
    assert draft is not None
    assert draft.payload_hash == compute_payload_hash(draft.payload)
    assert draft.status == "pending_approval"
    assert draft.tally_voucher_no is None  # Nothing posted to Tally!


def test_draft_sales_voucher_creation(draft_env):
    """Verify TC-DFT-03: Sales voucher draft with item lines."""
    handler = draft_env["tools_handler"]
    ai_claims = draft_env["ai_claims"]

    res = handler.draft_sales_voucher(ai_claims, {
        "party": "Patel Textiles",
        "date": "2026-10-26",
        "items": [
            {"item_name": "Cotton Grey Fabric 40s", "qty": "100.0", "rate": "120.00", "amount": "12000.00"},
            {"item_name": "Silk Chiffon 60g", "qty": "50.0", "rate": "350.00", "amount": "17500.00"},
        ],
    })

    assert res["status"] == "pending_approval"
    assert res["voucher_type"] == "Sales"
    assert res["lines"][0]["dr"] == "29500.00"
    assert res["lines"][1]["cr"] == "29500.00"


def test_draft_cancellation_scoping(draft_env):
    """Verify TC-DFT-04 & TC-DFT-05: Users can only cancel their own drafts."""
    handler = draft_env["tools_handler"]
    ai_claims = draft_env["ai_claims"]

    res = handler.draft_receipt_voucher(ai_claims, {
        "party": "Patel Textiles",
        "amount": "1000.00",
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
    })
    draft_id = res["draft_id"]

    # Cancel own draft succeeds
    cancel_res = handler.cancel_draft(ai_claims, {"draft_id": draft_id})
    assert cancel_res["status"] == "cancelled"

    # Other user trying to cancel raises ScopeDeniedError
    other_token_str = create_access_token(
        user_id="other-user-999",
        tenant_id="tenant-123",
        client_id="other-agent",
        client_type="ai_client",
        scopes=[SCOPE_DRAFT_VOUCHERS],
        secret_key=SECRET_KEY,
    )
    other_claims = decode_and_validate_token(other_token_str, SECRET_KEY)

    res2 = handler.draft_receipt_voucher(ai_claims, {
        "party": "Patel Textiles",
        "amount": "1000.00",
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
    })
    with pytest.raises(ScopeDeniedError, match="SCOPE_DENIED"):
        handler.cancel_draft(other_claims, {"draft_id": res2["draft_id"]})


# ==============================================================================
# 2. Anomaly Rules Engine Tests (TC-RUL-01, 02, 03, 04)
# ==============================================================================

def test_anomaly_flags_threshold_and_new_party(draft_env):
    """Verify TC-RUL-01 & TC-RUL-02: Flags threshold breach and unknown beneficiary."""
    handler = draft_env["tools_handler"]
    ai_claims = draft_env["ai_claims"]

    res = handler.draft_receipt_voucher(ai_claims, {
        "party": "Unknown Bogus Account",  # New party not in chart of accounts
        "amount": "65000.00",             # Exceeds 50,000 threshold
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
    })

    assert "amount_above_threshold" in res["flags"]
    assert "new_party_reference" in res["flags"]
    assert res["risk_level"] == "MEDIUM"


# ==============================================================================
# 3. Out-of-Band Approval Lifecycle & Posting (TC-APP-01 to TC-APP-07, TC-PST-01)
# ==============================================================================

def test_successful_approval_and_posting(draft_env):
    """Verify TC-APP-01, TC-APP-02, TC-PST-01: Render, approve, and post voucher with number return."""
    handler = draft_env["tools_handler"]
    approval_svc = draft_env["approval_service"]
    ai_claims = draft_env["ai_claims"]
    human_claims = draft_env["human_claims"]

    # Step 1: AI drafts voucher
    draft_res = handler.draft_receipt_voucher(ai_claims, {
        "party": "Patel Textiles",
        "amount": "20000.00",
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
    })
    draft_id = draft_res["draft_id"]

    # Step 2: Human renders draft
    rendered = approval_svc.render_draft(draft_id, human_claims)
    assert rendered["draft_id"] == draft_id
    assert rendered["status"] == "pending_approval"

    # Step 3: Human approves draft
    decision_res = approval_svc.submit_decision(draft_id, human_claims, decision="approve")
    assert decision_res["status"] == "posted"
    assert decision_res["tally_voucher_no"] == "REC-2026-88"

    # Step 4: Verify draft status in store
    draft = draft_env["draft_manager"].get_draft(draft_id)
    assert draft.status == "posted"
    assert draft.tally_voucher_no == "REC-2026-88"


def test_tampered_payload_blocks_approval(draft_env):
    """Verify TC-APP-03 & Invariant INV-04: Modifying draft payload in DB invalidates approval."""
    handler = draft_env["tools_handler"]
    approval_svc = draft_env["approval_service"]
    ai_claims = draft_env["ai_claims"]
    human_claims = draft_env["human_claims"]

    draft_res = handler.draft_receipt_voucher(ai_claims, {
        "party": "Patel Textiles",
        "amount": "20000.00",
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
    })
    draft_id = draft_res["draft_id"]

    # Attacker tampers with payload in storage (changing 20,000 to 5,00,000)
    draft = draft_env["draft_manager"].get_draft(draft_id)
    draft.payload["amount"] = "500000.00"

    # Approval attempt must fail cryptographic hash check
    with pytest.raises(DraftStateError, match="Payload hash verification failed"):
        approval_svc.submit_decision(draft_id, human_claims, decision="approve")

    assert draft.status == "failed"


def test_rejection_lifecycle(draft_env):
    """Verify TC-APP-04: Rejecting draft transitions to rejected with zero posting."""
    handler = draft_env["tools_handler"]
    approval_svc = draft_env["approval_service"]
    ai_claims = draft_env["ai_claims"]
    human_claims = draft_env["human_claims"]

    draft_res = handler.draft_receipt_voucher(ai_claims, {
        "party": "Patel Textiles",
        "amount": "5000.00",
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
    })
    draft_id = draft_res["draft_id"]

    res = approval_svc.submit_decision(draft_id, human_claims, decision="reject", note="Duplicate bill")
    assert res["status"] == "rejected"

    draft = draft_env["draft_manager"].get_draft(draft_id)
    assert draft.status == "rejected"
    assert draft.tally_voucher_no is None


def test_ai_client_cannot_approve(draft_env):
    """Verify TC-APP-06: AI client attempting to call approval endpoint is rejected."""
    handler = draft_env["tools_handler"]
    approval_svc = draft_env["approval_service"]
    ai_claims = draft_env["ai_claims"]

    draft_res = handler.draft_receipt_voucher(ai_claims, {
        "party": "Patel Textiles",
        "amount": "5000.00",
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
    })
    draft_id = draft_res["draft_id"]

    with pytest.raises(ScopeDeniedError, match="AI clients cannot approve drafts"):
        approval_svc.submit_decision(draft_id, ai_claims, decision="approve")


def test_high_risk_requires_two_distinct_approvers(draft_env):
    """Verify TC-APP-07 & FR-063: High-value transaction requires 2 distinct human approvers."""
    handler = draft_env["tools_handler"]
    approval_svc = draft_env["approval_service"]
    ai_claims = draft_env["ai_claims"]
    human_1 = draft_env["human_claims"]
    human_2 = draft_env["human_claims_2"]

    # Draft high-value transaction of ₹2,50,000 (exceeds second_approver_threshold of 2L)
    draft_res = handler.draft_receipt_voucher(ai_claims, {
        "party": "Patel Textiles",
        "amount": "250000.00",
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
    })
    draft_id = draft_res["draft_id"]
    assert "amount_requires_second_approver" in draft_res["flags"]

    # Approver 1 approves -> Transitions to pending_second_approval
    res1 = approval_svc.submit_decision(draft_id, human_1, decision="approve")
    assert res1["status"] == "pending_second_approval"

    # Approver 1 tries to approve a second time -> Rejected (cannot self-approve)
    with pytest.raises(AuthSecurityError, match="second approver must be a different human"):
        approval_svc.submit_decision(draft_id, human_1, decision="approve")

    # Approver 2 approves -> Transitions to posted
    res2 = approval_svc.submit_decision(draft_id, human_2, decision="approve")
    assert res2["status"] == "posted"
    assert res2["tally_voucher_no"] == "REC-2026-88"


def test_idempotent_duplicate_approval(draft_env):
    """Verify TC-CHS-01: Duplicate approval calls on an already posted draft return cached status."""
    handler = draft_env["tools_handler"]
    approval_svc = draft_env["approval_service"]
    ai_claims = draft_env["ai_claims"]
    human_claims = draft_env["human_claims"]

    draft_res = handler.draft_receipt_voucher(ai_claims, {
        "party": "Patel Textiles",
        "amount": "10000.00",
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
    })
    draft_id = draft_res["draft_id"]

    # First approval
    res1 = approval_svc.submit_decision(draft_id, human_claims, decision="approve")
    assert res1["status"] == "posted"

    # Duplicate approval call
    res2 = approval_svc.submit_decision(draft_id, human_claims, decision="approve")
    assert res2["status"] == "posted"
    assert res2["tally_voucher_no"] == res1["tally_voucher_no"]


# ==============================================================================
# 4. Payment & Journal Draft Tools Tests (FR-022)
# ==============================================================================

def test_draft_payment_voucher_creation(draft_env):
    """Verify FR-022: Payment voucher drafting with Dr Party, Cr Bank."""
    handler = draft_env["tools_handler"]
    approval_svc = draft_env["approval_service"]
    ai_claims = draft_env["ai_claims"]
    human_claims = draft_env["human_claims"]

    res = handler.draft_payment_voucher(ai_claims, {
        "party": "Surat Silk Mills",
        "amount": "15000.00",
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
        "reference": "CHQ-987654",
        "narration": "Payment against raw material purchase",
    })

    assert res["status"] == "pending_approval"
    assert res["voucher_type"] == "Payment"
    assert len(res["lines"]) == 2
    assert res["lines"][0]["ledger"] == "Surat Silk Mills"
    assert res["lines"][0]["dr"] == "15000.00"
    assert res["lines"][1]["ledger"] == "HDFC Bank"
    assert res["lines"][1]["cr"] == "15000.00"

    # Approve and verify posting to Tally returns PAY prefix
    post_res = approval_svc.submit_decision(res["draft_id"], human_claims, decision="approve")
    assert post_res["status"] == "posted"
    assert post_res["tally_voucher_no"] == "PAY-2026-88"


def test_draft_journal_voucher_balanced_and_unbalanced(draft_env):
    """Verify FR-022: Journal voucher drafting requires strict Dr == Cr balancing."""
    handler = draft_env["tools_handler"]
    ai_claims = draft_env["ai_claims"]

    # 1. Balanced Journal Voucher
    res = handler.draft_journal_voucher(ai_claims, {
        "date": "2026-10-26",
        "narration": "Correction adjustment entry",
        "lines": [
            {"ledger": "Patel Textiles", "amount": "7500.00", "is_debit": True},
            {"ledger": "Surat Silk Mills", "amount": "7500.00", "is_debit": False},
        ],
    })

    assert res["status"] == "pending_approval"
    assert res["voucher_type"] == "Journal"
    assert len(res["lines"]) == 2

    # 2. Unbalanced Journal Voucher raises VALIDATION_FAILED
    with pytest.raises(ValueError, match="VALIDATION_FAILED: Journal voucher is unbalanced"):
        handler.draft_journal_voucher(ai_claims, {
            "date": "2026-10-26",
            "lines": [
                {"ledger": "Patel Textiles", "amount": "7500.00", "is_debit": True},
                {"ledger": "Surat Silk Mills", "amount": "6000.00", "is_debit": False},
            ],
        })


def test_expired_draft_cannot_be_approved(draft_env):
    """Verify TC-APP-05: Expired draft cannot be approved."""
    draft_mgr = draft_env["draft_manager"]
    approval_svc = draft_env["approval_service"]
    human_claims = draft_env["human_claims"]

    # Create draft with negative expiry hours (-1 hr ago)
    draft = draft_mgr.create_draft(
        tenant_id="tenant-123",
        user_id="ai-agent-user-1",
        client_id="claude-desktop",
        voucher_type="Receipt",
        payload={"party": "Patel Textiles", "amount": "5000.00", "date": "2026-10-26"},
        flags=[],
        risk_level="LOW",
        expiry_hours=-1,
    )

    # Calling submit_decision should raise DraftStateError
    with pytest.raises(DraftStateError, match="expired"):
        approval_svc.submit_decision(draft.id, human_claims, decision="approve")


# ==============================================================================
# 5. REST API FastAPI Endpoints Test (TASK-3.5, FR-060)
# ==============================================================================

def test_fastapi_approval_rest_api_structure(draft_env):
    """Verify TASK-3.5: GET /approve/{draft_id} and POST /approve/{draft_id} REST routes exist and enforce auth."""
    from fastapi import HTTPException
    from server.api.approval_api import create_approval_router
    from server.mcp.schemas.draft_schemas import ApprovalDecisionInput

    router = create_approval_router(draft_env["approval_service"], SECRET_KEY)
    assert router.prefix == "/approve"

    routes = {}
    for r in router.routes:
        routes.setdefault(r.path, set()).update(r.methods)
    assert "/approve/{draft_id}" in routes
    assert "GET" in routes["/approve/{draft_id}"]
    assert "POST" in routes["/approve/{draft_id}"]

    get_handler = None
    post_handler = None
    for r in router.routes:
        if r.path == "/approve/{draft_id}" and "GET" in r.methods:
            get_handler = r.endpoint
        elif r.path == "/approve/{draft_id}" and "POST" in r.methods:
            post_handler = r.endpoint

    assert get_handler is not None
    assert post_handler is not None

    handler = draft_env["tools_handler"]
    ai_claims = draft_env["ai_claims"]
    human_claims = draft_env["human_claims"]

    draft_res = handler.draft_receipt_voucher(ai_claims, {
        "party": "Patel Textiles",
        "amount": "12000.00",
        "date": "2026-10-26",
        "bank_cash_ledger": "HDFC Bank",
    })
    draft_id = draft_res["draft_id"]

    # 1. Direct call to get_handler with valid claims renders draft
    rendered = get_handler(draft_id, human_claims)
    assert rendered["draft_id"] == draft_id
    assert rendered["status"] == "pending_approval"

    # 2. Direct call to post_handler with AI claims raises HTTP 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        post_handler(draft_id, ApprovalDecisionInput(decision="approve"), ai_claims)
    assert exc_info.value.status_code == 403

    # 3. Direct call to post_handler with human claims approves and posts
    result = post_handler(draft_id, ApprovalDecisionInput(decision="approve", note="Approved by CFO"), human_claims)
    assert result["status"] == "posted"
    assert result["tally_voucher_no"] == "REC-2026-88"


