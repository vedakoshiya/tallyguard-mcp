"""Sensitive Data Redaction Engine for TallyGuard MCP Audit Logs.

Satisfies FR-083:
Automatically redacts PAN numbers, bank account numbers, passwords, and bearer tokens
from tool arguments before logging to the immutable audit trail.
"""

import re
from typing import Any, Dict, List, Union

# Regex for Indian Permanent Account Number (PAN): 5 letters, 4 digits, 1 letter
PAN_REGEX = re.compile(r"\b([A-Z]{5})(\d{4})([A-Z])\b", flags=re.IGNORECASE)

# Regex for Indian Bank Account Numbers (9 to 18 consecutive digits)
BANK_ACCOUNT_REGEX = re.compile(r"\b(\d{4,14})(\d{4})\b")

# Keywords that indicate sensitive credentials
CREDENTIAL_KEYS = {
    "password", "secret", "token", "access_token", "api_key",
    "authorization", "private_key", "pin", "otp"
}


def redact_string(val: str) -> str:
    """Mask sensitive patterns in a single string."""
    # Redact PAN (e.g., AAACS1234F -> *****1234F)
    masked = PAN_REGEX.sub(r"*****\2\3", val)
    # Redact Bank Account Numbers (e.g., 123456789012 -> ********9012)
    masked = BANK_ACCOUNT_REGEX.sub(r"****\2", masked)
    return masked


def redact_sensitive_data(data: Any) -> Any:
    """Recursively redact sensitive fields and values from arguments dictionary or list."""
    if isinstance(data, str):
        return redact_string(data)

    if isinstance(data, dict):
        redacted_dict: Dict[str, Any] = {}
        for key, val in data.items():
            key_lower = str(key).lower()
            if any(cred in key_lower for cred in CREDENTIAL_KEYS):
                redacted_dict[key] = "[REDACTED]"
            else:
                redacted_dict[key] = redact_sensitive_data(val)
        return redacted_dict

    if isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]

    return data
