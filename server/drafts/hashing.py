"""Cryptographic Draft Payload Hashing Engine for TallyGuard MCP.

Implements Invariant INV-04 and FR-065.
Calculates canonical SHA-256 digests over draft transaction payloads.
Ensures that once a draft is created, it cannot be tampered with in storage
or modified prior to human approval and bridge posting.
"""

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Serialize payload to deterministic, sorted, whitespace-compact JSON string."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """Compute SHA-256 hex digest over canonical draft payload."""
    canonical_repr = canonical_json(payload)
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


def verify_payload_hash(payload: dict[str, Any], expected_hash: str) -> bool:
    """Verify that current payload matches expected SHA-256 digest."""
    computed = compute_payload_hash(payload)
    return computed == expected_hash
