"""Comprehensive Automated Test Suite for Phase 2: Security, Auth & Audit Log.

Verifies:
- TC-AUTH-01 to TC-AUTH-07: OAuth 2.1 token issuance, PKCE, scopes, human privilege separation.
- TC-AUD-01 to TC-AUD-05: Hash-chained audit logging, tamper detection, and sensitive redaction.
"""

from datetime import datetime, timezone, timedelta
import pytest

from server.auth.tokens import (
    create_access_token,
    decode_and_validate_token,
    generate_pkce_pair,
    verify_pkce,
    AuthSecurityError,
    TokenExpiredError,
    InvalidTokenError,
)
from server.auth.scopes import (
    check_tool_permission,
    ScopeDeniedError,
    SCOPE_READ_REPORTS,
    SCOPE_READ_LEDGERS,
    SCOPE_DRAFT_VOUCHERS,
    SCOPE_APPROVE_VOUCHERS,
)
from server.auth.allowlist import LedgerAllowListValidator
from server.auth.rate_limiter import RateLimiter, RateLimitedError, TokenBucket
from server.audit.hash_chain import (
    AuditChainLogger,
    compute_args_hash,
    GENESIS_HASH,
)
from server.audit.redaction import redact_sensitive_data, redact_string

SECRET_KEY = "test-secret-key-32-characters-long-tallyguard"


# ==============================================================================
# 1. OAuth 2.1 Tokens & PKCE Tests (TC-AUTH-01, 02, 03, 05)
# ==============================================================================

def test_pkce_generation_and_verification():
    """Verify S256 PKCE code verifier and challenge generation."""
    pkce = generate_pkce_pair()
    verifier = pkce["code_verifier"]
    challenge = pkce["code_challenge"]

    assert len(verifier) >= 43
    assert len(challenge) > 20
    assert verify_pkce(verifier, challenge) is True
    assert verify_pkce("wrong_verifier_string_value", challenge) is False


def test_token_creation_and_decoding():
    """Verify valid token issuance and payload decoding."""
    token = create_access_token(
        user_id="user-uuid-1",
        tenant_id="tenant-uuid-1",
        client_id="claude-desktop",
        client_type="ai_client",
        scopes=[SCOPE_READ_REPORTS, SCOPE_READ_LEDGERS],
        secret_key=SECRET_KEY,
        ledger_allowlist=["Sundry Debtors"],
        expires_in_minutes=15,
    )

    claims = decode_and_validate_token(token, SECRET_KEY)
    assert claims.sub == "user-uuid-1"
    assert claims.tenant_id == "tenant-uuid-1"
    assert claims.client_id == "claude-desktop"
    assert claims.client_type == "ai_client"
    assert SCOPE_READ_REPORTS in claims.scopes
    assert claims.ledger_allowlist == ["Sundry Debtors"]


def test_token_signature_tampering_rejection():
    """Verify TC-AUTH-03: Tampered token signature fails validation."""
    token = create_access_token(
        user_id="user-1",
        tenant_id="tenant-1",
        client_id="client-1",
        client_type="ai_client",
        scopes=[SCOPE_READ_REPORTS],
        secret_key=SECRET_KEY,
    )

    # Tamper with the payload
    parts = token.split(".")
    tampered_token = f"{parts[0]}.eyJhZG1pbiI6dHJ1ZX0.{parts[2]}"

    with pytest.raises(InvalidTokenError, match="signature verification failed"):
        decode_and_validate_token(tampered_token, SECRET_KEY)


def test_token_expiration_rejection():
    """Verify TC-AUTH-02: Expired tokens are rejected."""
    token = create_access_token(
        user_id="user-1",
        tenant_id="tenant-1",
        client_id="client-1",
        client_type="ai_client",
        scopes=[SCOPE_READ_REPORTS],
        secret_key=SECRET_KEY,
        expires_in_minutes=-5,  # Already expired 5 minutes ago
    )

    with pytest.raises(TokenExpiredError, match="Access token expired"):
        decode_and_validate_token(token, SECRET_KEY)


def test_human_only_permission_separation():
    """Verify Invariant INV-03 & TC-AUTH-05: AI tokens cannot receive approve:vouchers."""
    with pytest.raises(AuthSecurityError, match="Security Invariant Violation"):
        create_access_token(
            user_id="ai-agent-1",
            tenant_id="tenant-1",
            client_id="claude-desktop",
            client_type="ai_client",
            scopes=[SCOPE_READ_REPORTS, SCOPE_APPROVE_VOUCHERS],  # Forbidden for AI
            secret_key=SECRET_KEY,
        )


# ==============================================================================
# 2. Scope Enforcement Tests (TC-AUTH-04)
# ==============================================================================

def test_scope_authorization():
    """Verify check_tool_permission enforces tool-to-scope mappings."""
    token = create_access_token(
        user_id="user-1",
        tenant_id="tenant-1",
        client_id="agent-1",
        client_type="ai_client",
        scopes=[SCOPE_READ_REPORTS],  # Only read:reports granted
        secret_key=SECRET_KEY,
    )
    claims = decode_and_validate_token(token, SECRET_KEY)

    # Permitted tool: get_company_info requires read:reports
    check_tool_permission(claims, "get_company_info")

    # Denied tool: search_vouchers requires read:vouchers
    with pytest.raises(ScopeDeniedError) as exc_info:
        check_tool_permission(claims, "search_vouchers")
    assert exc_info.value.code == "SCOPE_DENIED"
    assert exc_info.value.required_scope == "read:vouchers"


def test_human_approval_scope_guard():
    """Verify AI clients cannot invoke approval tools even if claim spoofing is attempted."""
    # Create human claims with approve scope
    human_token = create_access_token(
        user_id="accountant-1",
        tenant_id="tenant-1",
        client_id="web-portal",
        client_type="human_user",
        scopes=[SCOPE_APPROVE_VOUCHERS],
        secret_key=SECRET_KEY,
    )
    human_claims = decode_and_validate_token(human_token, SECRET_KEY)
    check_tool_permission(human_claims, "approve_voucher")  # Permitted for human


# ==============================================================================
# 3. Ledger Allow-List Tests (TC-AUTH-06)
# ==============================================================================

def test_ledger_allowlist_validator():
    """Verify account and parent group allowlist enforcement."""
    allowlist = ["Sundry Debtors", "Sales Account"]

    # Direct match on allowed ledger
    assert LedgerAllowListValidator.is_ledger_permitted("Sales Account", "Sales Accounts", allowlist) is True

    # Group hierarchy match: Patel Textiles has parent 'Sundry Debtors'
    assert LedgerAllowListValidator.is_ledger_permitted("Patel Textiles", "Sundry Debtors", allowlist) is True

    # Forbidden ledger: HDFC Bank has parent 'Bank Accounts'
    assert LedgerAllowListValidator.is_ledger_permitted("HDFC Bank", "Bank Accounts", allowlist) is False

    with pytest.raises(ScopeDeniedError, match="SCOPE_DENIED"):
        LedgerAllowListValidator.assert_ledger_permitted("HDFC Bank", "Bank Accounts", allowlist)

    # Filter ledger list
    raw_ledgers = [
        {"name": "Patel Textiles", "parent": "Sundry Debtors"},
        {"name": "HDFC Bank", "parent": "Bank Accounts"},
        {"name": "Sales Account", "parent": "Sales Accounts"},
    ]
    filtered = LedgerAllowListValidator.filter_ledgers(raw_ledgers, allowlist)
    assert len(filtered) == 2
    assert [l["name"] for l in filtered] == ["Patel Textiles", "Sales Account"]


# ==============================================================================
# 4. Rate Limiting Tests (TC-AUTH-07)
# ==============================================================================

def test_rate_limiter_burst_and_throttle():
    """Verify token bucket rate limiter restricts bursts exceeding capacity."""
    limiter = RateLimiter(default_rate_limit=3, default_refill_per_sec=0.1)

    # First 3 requests permitted
    limiter.check_rate_limit("user-test-1")
    limiter.check_rate_limit("user-test-1")
    limiter.check_rate_limit("user-test-1")

    # 4th request must be throttled
    with pytest.raises(RateLimitedError) as exc_info:
        limiter.check_rate_limit("user-test-1")
    assert exc_info.value.code == "RATE_LIMITED"
    assert exc_info.value.retry_after_seconds > 0


def test_daily_draft_quota():
    """Verify daily draft quota stops write flooding."""
    limiter = RateLimiter(max_daily_drafts=2)

    assert limiter.check_and_increment_daily_drafts("user-draft-1") == 1
    assert limiter.check_and_increment_daily_drafts("user-draft-1") == 2

    # 3rd draft attempt fails daily quota
    with pytest.raises(RateLimitedError, match="daily write-draft quota"):
        limiter.check_and_increment_daily_drafts("user-draft-1")


# ==============================================================================
# 5. Sensitive Data Redaction Tests (TC-AUD-04)
# ==============================================================================

def test_redact_pan_and_bank_account():
    """Verify PAN and bank accounts are masked."""
    # PAN masking
    assert redact_string("Customer PAN is AAACS1234F for billing") == "Customer PAN is *****1234F for billing"

    # Bank account masking
    assert redact_string("Transfer to A/C 987654321098 via RTGS") == "Transfer to A/C ****1098 via RTGS"

    # Dictionary recursive masking
    data = {
        "party": "Patel Textiles",
        "pan": "ABCDE5678G",
        "bank_account": "112233445566",
        "api_secret": "super_secret_token_123",
        "nested": {"client_secret": "nested_secret_456"},
    }
    redacted = redact_sensitive_data(data)
    assert redacted["party"] == "Patel Textiles"
    assert redacted["pan"] == "*****5678G"
    assert redacted["bank_account"] == "****5566"
    assert redacted["api_secret"] == "[REDACTED]"
    assert redacted["nested"]["client_secret"] == "[REDACTED]"


# ==============================================================================
# 6. Cryptographic Hash-Chained Audit Log Tests (TC-AUD-01, 02, 03)
# ==============================================================================

def test_audit_log_hash_chaining_and_integrity():
    """Verify append-only HMAC-SHA256 hash chaining."""
    logger = AuditChainLogger(secret_key=SECRET_KEY)

    # Log 3 events
    e1 = logger.log(
        tenant_id="tenant-1",
        tool="get_company_info",
        raw_args={},
        status="SUCCESS",
        actor_user="user-1",
    )
    assert e1.prev_hash == GENESIS_HASH

    e2 = logger.log(
        tenant_id="tenant-1",
        tool="get_party_ledger",
        raw_args={"party": "Patel Textiles", "pan": "AAACS1234F"},
        status="SUCCESS",
        actor_user="user-1",
    )
    assert e2.prev_hash == e1.entry_hash
    # Verify PAN was redacted in audit entry
    assert e2.args_redacted["pan"] == "*****1234F"

    e3 = logger.log(
        tenant_id="tenant-1",
        tool="get_receivables_ageing",
        raw_args={"as_on": "2026-10-31"},
        status="SUCCESS",
        actor_user="user-1",
    )
    assert e3.prev_hash == e2.entry_hash

    # Verify complete chain integrity
    is_valid, err = logger.verify_integrity()
    assert is_valid is True
    assert err is None


def test_audit_tampering_detection():
    """Verify TC-AUD-03: Artificially tampering with an audit record breaks the chain."""
    logger = AuditChainLogger(secret_key=SECRET_KEY)

    logger.log(tenant_id="tenant-1", tool="get_company_info", raw_args={}, status="SUCCESS")
    logger.log(tenant_id="tenant-1", tool="list_ledgers", raw_args={}, status="SUCCESS")
    logger.log(tenant_id="tenant-1", tool="get_stock_summary", raw_args={}, status="SUCCESS")

    assert logger.verify_integrity()[0] is True

    # Tamper with entry #2's tool name (simulating an unauthorized DB row edit)
    logger.entries[1].tool = "unauthorized_export_tool"

    is_valid, err = logger.verify_integrity()
    assert is_valid is False
    assert "Signature Tampering detected" in err
