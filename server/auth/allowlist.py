"""Per-User Ledger and Group Allow-List Validator for TallyGuard MCP.

Implements US-07 and FR-051.
Restricts specific users or AI sessions to an approved subset of accounts/groups
(e.g., restricting a sales bot to 'Sundry Debtors' and 'Sales Accounts').
"""

from typing import Any, Dict, List, Optional
from server.auth.scopes import ScopeDeniedError


class LedgerAllowListValidator:
    """Enforces account-level and group-level data scoping."""

    @staticmethod
    def is_ledger_permitted(
        ledger_name: str,
        parent_group: Optional[str],
        allowlist: Optional[List[str]],
    ) -> bool:
        """Check if a specific ledger is within the permitted allowlist.

        Args:
            ledger_name: Name of the ledger account.
            parent_group: Parent group in Chart of Accounts (e.g. 'Sundry Debtors').
            allowlist: Permitted accounts or groups. If None, unrestricted.

        Returns:
            True if permitted, False otherwise.
        """
        if allowlist is None:
            return True

        normalized_allowlist = {entry.strip().lower() for entry in allowlist}
        ledger_norm = ledger_name.strip().lower()

        # Direct ledger match
        if ledger_norm in normalized_allowlist:
            return True

        # Group hierarchy match (e.g. allowlist has 'sundry debtors' and ledger's parent is 'sundry debtors')
        if parent_group and parent_group.strip().lower() in normalized_allowlist:
            return True

        return False

    @classmethod
    def assert_ledger_permitted(
        cls,
        ledger_name: str,
        parent_group: Optional[str],
        allowlist: Optional[List[str]],
    ) -> None:
        """Assert that a ledger is permitted, raising ScopeDeniedError on failure."""
        if not cls.is_ledger_permitted(ledger_name, parent_group, allowlist):
            raise ScopeDeniedError(
                f"SCOPE_DENIED: Access to ledger '{ledger_name}' (group: '{parent_group}') "
                f"is denied by account allow-list policy.",
                required_scope=f"ledger:{ledger_name}",
                granted_scopes=allowlist or [],
            )

    @classmethod
    def filter_ledgers(
        cls,
        ledgers: List[Dict[str, Any]],
        allowlist: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """Filter a list of ledger dictionaries against an allowlist."""
        if allowlist is None:
            return ledgers

        return [
            l for l in ledgers
            if cls.is_ledger_permitted(
                ledger_name=l.get("name", ""),
                parent_group=l.get("parent", ""),
                allowlist=allowlist,
            )
        ]
