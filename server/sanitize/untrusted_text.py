"""Untrusted Text Sanitization and Delimitation Engine for TallyGuard MCP.

Satisfies FR-080, FR-081, and STRIDE mitigation against prompt injection.
All free-text sourced from Tally (narrations, ledger names, remarks, addresses)
is treated as untrusted data:
1. Strips non-printable ASCII control characters.
2. Detects instruction-like patterns (e.g., prompt injection, jailbreaks, system role-play).
3. Caps excessive length to prevent context flooding.
4. Wraps in an immutable, delimited `untrusted_text` schema.
"""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional

# Default maximum string lengths to prevent context flooding
DEFAULT_MAX_NARRATION_LENGTH = 1000
DEFAULT_MAX_NAME_LENGTH = 200

# Regex for non-printable control characters (excluding standard whitespace \t, \n, \r)
CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# High-risk instruction-like patterns for prompt injection detection
INJECTION_PATTERNS = [
    (r"(?i)\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b", "instruction_override"),
    (r"(?i)\b(system\s+prompt|system\s+instructions?)\b", "system_prompt_reference"),
    (r"(?i)\[/?(system|inst|assistant)", "role_markup"),
    (r"(?i)<(system|instructions?|prompt)>.*?</\1>", "xml_instruction_tag"),
    (r"(?i)\b(you\s+are\s+now|act\s+as\s+a)\b", "roleplay_prompt"),
    (r"(?i)\b(dan|do\s+anything\s+now|hypothetical\s+simulation|jailbreak)\b", "roleplay_prompt"),
    (r"(?i)\b(override|bypass)\s+.*(approval|safety|portal|guidelines|check)\b", "instruction_override"),
    (r"(?i)\b(override_scope|approve:vouchers)\b", "instruction_override"),
    (r"(?i)```(json|xml)?", "markup_code_injection"),
    (r"(?i)\b(delete|drop|wipe)\s+.*?\b(vouchers?|tables?|databases?|ledgers?)\b", "destructive_command"),
    (r"(?i)\b(post|create|transfer)\s+(a\s+)?(payment|receipt|voucher)\s+(of|to)\b", "unauthorized_transaction_instruction"),
    (r"(?i)</?untrusted_text>", "delimiter_injection"),
    (r"(?i)</?(voucher|envelope|importdata|requestdata|narration|body|header)>", "xml_markup_injection"),
    (r"(?i)\b(print\s+out|export|dump)\s+.*(secret|key|password|credential|jwt|pan)\b", "data_exfiltration_pattern"),
    (r"(?i)\bexfiltrat(e|ion)|send\s+to\s+https?://", "data_exfiltration_pattern"),
]


@dataclass(frozen=True)
class SanitizedText:
    """Delimited structure for untrusted text fields."""

    content: str
    original_length: int
    truncated: bool
    sanitized: bool
    suspicious: bool
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to standard MCP JSON-serializable dictionary."""
        return {
            "untrusted_text": {
                "content": self.content,
                "original_length": self.original_length,
                "truncated": self.truncated,
                "sanitized": self.sanitized,
                "suspicious": self.suspicious,
                "flags": self.flags,
            }
        }


def sanitize_untrusted_text(
    raw_text: Optional[str],
    max_length: int = DEFAULT_MAX_NARRATION_LENGTH,
) -> SanitizedText:
    """Sanitize and delimit untrusted text sourced from Tally books.

    Args:
        raw_text: Raw string from Tally (e.g. voucher narration or party name).
        max_length: Maximum allowed character length before truncation.

    Returns:
        SanitizedText instance with safety flags.
    """
    if raw_text is None:
        return SanitizedText(
            content="",
            original_length=0,
            truncated=False,
            sanitized=False,
            suspicious=False,
            flags=[],
        )

    original_length = len(raw_text)
    sanitized = False
    flags: List[str] = []

    # 1. Strip non-printable control characters
    cleaned_text = CONTROL_CHAR_REGEX.sub("", raw_text)
    if len(cleaned_text) != original_length:
        sanitized = True
        flags.append("stripped_control_characters")

    # 2. Neutralize delimiter escape sequences
    if "</untrusted_text>" in cleaned_text or "<untrusted_text>" in cleaned_text:
        cleaned_text = cleaned_text.replace("</untrusted_text>", "&lt;/untrusted_text&gt;").replace("<untrusted_text>", "&lt;untrusted_text&gt;")
        sanitized = True

    # 2. Check for prompt injection and instruction-like patterns
    for pattern, flag_name in INJECTION_PATTERNS:
        if re.search(pattern, cleaned_text):
            flags.append(flag_name)

    suspicious = len(flags) > 0 and any(f != "stripped_control_characters" for f in flags)

    # 3. Output size capping / truncation
    truncated = False
    if len(cleaned_text) > max_length:
        truncated = True
        cleaned_text = cleaned_text[:max_length] + f" [TRUNCATED: original was {original_length} chars]"
        sanitized = True
        flags.append("length_truncated")

    return SanitizedText(
        content=cleaned_text,
        original_length=original_length,
        truncated=truncated,
        sanitized=sanitized or (cleaned_text != raw_text),
        suspicious=suspicious,
        flags=flags,
    )
