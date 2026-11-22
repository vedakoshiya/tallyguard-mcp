"""Cryptographic Hash-Chained Audit Log Engine for TallyGuard MCP.

Implements FR-084, US-06, and Invariant INV-07.
Provides tamper-evident, append-only audit logging using HMAC-SHA256 chaining.
Each entry cryptographically binds to the previous entry's hash, making silent
history tampering or row deletion mathematically detectable.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import hmac
import json
from typing import Any, Dict, List, Optional, Tuple
import uuid

from server.audit.redaction import redact_sensitive_data

GENESIS_HASH = "0" * 64


def canonical_json(obj: Any) -> str:
    """Serialize object to canonical, deterministic JSON (sorted keys, compact)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_args_hash(args: Optional[Dict[str, Any]]) -> str:
    """Compute SHA-256 digest of canonical arguments dictionary."""
    if not args:
        canonical_str = "{}"
    else:
        canonical_str = canonical_json(args)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def compute_entry_hash(
    secret_key: str,
    prev_hash: str,
    correlation_id: str,
    tenant_id: str,
    tool: str,
    args_hash: str,
    status: str,
    created_at_iso: str,
) -> str:
    """Compute HMAC-SHA256 hash over chained entry metadata."""
    signing_payload = f"{prev_hash}|{correlation_id}|{tenant_id}|{tool}|{args_hash}|{status}|{created_at_iso}"
    return hmac.new(
        secret_key.encode("utf-8"),
        signing_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@dataclass
class AuditEntry:
    """Immutable audit log record matching PostgreSQL schema."""

    id: int
    tenant_id: str
    actor_user: Optional[str]
    client_id: Optional[str]
    tool: str
    args_hash: str
    args_redacted: Optional[Dict[str, Any]]
    result_summary: Optional[Dict[str, Any]]
    status: str
    correlation_id: str
    prev_hash: str
    entry_hash: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuditChainLogger:
    """In-memory or storage-backed hash-chained audit logger."""

    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.entries: List[AuditEntry] = []
        self._last_hash = GENESIS_HASH

    @property
    def last_hash(self) -> str:
        return self._last_hash

    def log(
        self,
        tenant_id: str,
        tool: str,
        raw_args: Optional[Dict[str, Any]],
        status: str,
        actor_user: Optional[str] = None,
        client_id: Optional[str] = None,
        result_summary: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        timestamp_iso: Optional[str] = None,
    ) -> AuditEntry:
        """Create and append an audit record cryptographically bound to the prior hash."""
        corr_id = correlation_id or str(uuid.uuid4())
        created_at = timestamp_iso or datetime.now(timezone.utc).isoformat()
        args_hash = compute_args_hash(raw_args)
        args_redacted = redact_sensitive_data(raw_args) if raw_args else {}

        prev_hash = self._last_hash

        entry_hash = compute_entry_hash(
            secret_key=self.secret_key,
            prev_hash=prev_hash,
            correlation_id=corr_id,
            tenant_id=tenant_id,
            tool=tool,
            args_hash=args_hash,
            status=status,
            created_at_iso=created_at,
        )

        entry_id = len(self.entries) + 1
        entry = AuditEntry(
            id=entry_id,
            tenant_id=tenant_id,
            actor_user=actor_user,
            client_id=client_id,
            tool=tool,
            args_hash=args_hash,
            args_redacted=args_redacted,
            result_summary=result_summary,
            status=status,
            correlation_id=corr_id,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
            created_at=created_at,
        )

        self.entries.append(entry)
        self._last_hash = entry_hash
        return entry

    def verify_integrity(self) -> Tuple[bool, Optional[str]]:
        """Verify the cryptographic hash chain across all stored entries.

        Returns:
            (True, None) if completely valid.
            (False, error_description) if any entry was altered, inserted, or deleted.
        """
        expected_prev = GENESIS_HASH

        for idx, entry in enumerate(self.entries):
            # 1. Verify prev_hash matches prior entry_hash
            if entry.prev_hash != expected_prev:
                return (
                    False,
                    f"Broken Chain at entry #{entry.id} (index {idx}): "
                    f"prev_hash '{entry.prev_hash}' does not match expected '{expected_prev}'.",
                )

            # 2. Recompute entry_hash and assert exact match
            recomputed_hash = compute_entry_hash(
                secret_key=self.secret_key,
                prev_hash=entry.prev_hash,
                correlation_id=entry.correlation_id,
                tenant_id=entry.tenant_id,
                tool=entry.tool,
                args_hash=entry.args_hash,
                status=entry.status,
                created_at_iso=entry.created_at,
            )

            if not hmac.compare_digest(recomputed_hash, entry.entry_hash):
                return (
                    False,
                    f"Signature Tampering detected at entry #{entry.id} (index {idx}): "
                    f"stored hash '{entry.entry_hash}' does not match recomputed '{recomputed_hash}'.",
                )

            expected_prev = entry.entry_hash

        return True, None
