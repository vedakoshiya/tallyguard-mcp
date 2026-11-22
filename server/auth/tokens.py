"""OAuth 2.1 Token Engine & PKCE Verification for TallyGuard MCP.

Enforces:
1. Short-lived access tokens with cryptographic signatures (HS256/RS256).
2. PKCE (Proof Key for Code Exchange) S256 verification (FR-050).
3. Non-negotiable privilege separation: Rejects any attempt to issue the
   'approve:vouchers' capability to an AI client token (FR-053, INV-03).
"""

import base64
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import secrets
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class AuthSecurityError(Exception):
    """Base exception for authentication and token security violations."""
    pass


class TokenExpiredError(AuthSecurityError):
    """Raised when an access token has expired."""
    pass


class InvalidTokenError(AuthSecurityError):
    """Raised when an access token is malformed, has an invalid signature, or fails validation."""
    pass


class TokenClaims(BaseModel):
    """Strict model for decoded JWT claims."""

    model_config = ConfigDict(extra="forbid")

    sub: str = Field(..., description="Subject identifier (User UUID)")
    tenant_id: str = Field(..., description="Tenant UUID")
    client_id: str = Field(..., description="Client identifier (e.g. claude-desktop, custom-agent)")
    client_type: str = Field(
        ...,
        pattern=r"^(ai_client|human_user)$",
        description="Type of client: 'ai_client' or 'human_user'",
    )
    scopes: List[str] = Field(default_factory=list, description="Granted OAuth scopes")
    ledger_allowlist: Optional[List[str]] = Field(
        default=None,
        description="Optional list of permitted ledgers or groups",
    )
    exp: int = Field(..., description="Expiration timestamp (seconds since epoch)")
    iat: int = Field(..., description="Issued-at timestamp (seconds since epoch)")
    jti: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique JWT ID")


def generate_pkce_pair(verifier_length: int = 64) -> Dict[str, str]:
    """Generate OAuth 2.1 PKCE code_verifier and S256 code_challenge."""
    if verifier_length < 43 or verifier_length > 128:
        raise ValueError("PKCE code_verifier length must be between 43 and 128 characters.")

    raw_bytes = secrets.token_bytes(verifier_length)
    code_verifier = base64.urlsafe_b64encode(raw_bytes).decode("utf-8").rstrip("=")[:verifier_length]

    # S256 code_challenge = Base64URL-Encode(SHA256(ASCII(code_verifier)))
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    return {
        "code_verifier": code_verifier,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """Verify that SHA256 of code_verifier matches the code_challenge."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed_challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return hmac.compare_digest(computed_challenge, code_challenge)


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _base64url_decode(s: str) -> bytes:
    padding = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + padding)


def create_access_token(
    user_id: str,
    tenant_id: str,
    client_id: str,
    client_type: str,
    scopes: List[str],
    secret_key: str,
    ledger_allowlist: Optional[List[str]] = None,
    expires_in_minutes: int = 30,
) -> str:
    """Create a signed JWT access token.

    Enforces Invariant INV-03: AI client tokens can NEVER receive 'approve:vouchers'.
    """
    if client_type == "ai_client" and "approve:vouchers" in scopes:
        raise AuthSecurityError(
            "Security Invariant Violation: 'approve:vouchers' capability cannot be granted "
            "to AI client tokens. Approvals are strictly reserved for human identities."
        )

    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_in_minutes)

    claims = TokenClaims(
        sub=user_id,
        tenant_id=tenant_id,
        client_id=client_id,
        client_type=client_type,
        scopes=scopes,
        ledger_allowlist=ledger_allowlist,
        iat=int(now.timestamp()),
        exp=int(exp.timestamp()),
    )

    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _base64url_encode(
        json.dumps(claims.model_dump(), separators=(",", ":")).encode("utf-8")
    )

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_and_validate_token(token_str: str, secret_key: str) -> TokenClaims:
    """Validate token signature and expiration, returning TokenClaims.

    Raises:
        TokenExpiredError: If token expired.
        InvalidTokenError: If token signature mismatch or format invalid.
    """
    parts = token_str.strip().split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Malformed JWT token. Expected exactly three dot-separated segments.")

    header_b64, payload_b64, signature_b64 = parts

    # 1. Verify Signature
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        provided_sig = _base64url_decode(signature_b64)
    except Exception as e:
        raise InvalidTokenError("Invalid base64 signature in token.") from e

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise InvalidTokenError("JWT signature verification failed. Token has been tampered with.")

    # 2. Decode payload
    try:
        payload_json = json.loads(_base64url_decode(payload_b64).decode("utf-8"))
        claims = TokenClaims.model_validate(payload_json)
    except Exception as e:
        raise InvalidTokenError(f"Invalid JWT claims payload: {str(e)}") from e

    # 3. Check expiration
    now_ts = int(datetime.now(timezone.utc).timestamp())
    if claims.exp < now_ts:
        raise TokenExpiredError(
            f"Access token expired at timestamp {claims.exp} (current time: {now_ts})."
        )

    # 4. Enforce Invariant INV-03 check on decoded tokens
    if claims.client_type == "ai_client" and "approve:vouchers" in claims.scopes:
        raise AuthSecurityError(
            "Security Invariant Violation: Found 'approve:vouchers' on an AI client token."
        )

    return claims
