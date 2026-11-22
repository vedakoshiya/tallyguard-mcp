"""Granular Scope Authorization Engine for TallyGuard MCP.

Implements FR-051, FR-053, and US-07.
Defines valid system scopes, maps MCP tools to required capabilities,
and enforces strict access boundaries.
"""


from server.auth.tokens import TokenClaims

# System OAuth Scopes
SCOPE_READ_REPORTS = "read:reports"
SCOPE_READ_LEDGERS = "read:ledgers"
SCOPE_READ_VOUCHERS = "read:vouchers"
SCOPE_READ_STOCK = "read:stock"
SCOPE_DRAFT_VOUCHERS = "draft:vouchers"
SCOPE_APPROVE_VOUCHERS = "approve:vouchers"  # HUMAN ONLY
SCOPE_ADMIN_USERS = "admin:users"

ALL_VALID_SCOPES: set[str] = {
    SCOPE_READ_REPORTS,
    SCOPE_READ_LEDGERS,
    SCOPE_READ_VOUCHERS,
    SCOPE_READ_STOCK,
    SCOPE_DRAFT_VOUCHERS,
    SCOPE_APPROVE_VOUCHERS,
    SCOPE_ADMIN_USERS,
}

# Mapping of MCP tools to required scopes
TOOL_SCOPE_REQUIREMENTS: dict[str, str] = {
    "get_company_info": SCOPE_READ_REPORTS,
    "list_ledgers": SCOPE_READ_LEDGERS,
    "get_party_ledger": SCOPE_READ_LEDGERS,
    "get_receivables_ageing": SCOPE_READ_REPORTS,
    "get_payables_ageing": SCOPE_READ_REPORTS,
    "search_vouchers": SCOPE_READ_VOUCHERS,
    "get_stock_summary": SCOPE_READ_STOCK,
    "get_gst_summary": SCOPE_READ_REPORTS,
    "get_trial_balance": SCOPE_READ_REPORTS,
    "get_profit_and_loss": SCOPE_READ_REPORTS,
    "get_balance_sheet": SCOPE_READ_REPORTS,
    "draft_receipt_voucher": SCOPE_DRAFT_VOUCHERS,
    "draft_sales_voucher": SCOPE_DRAFT_VOUCHERS,
    "draft_payment_voucher": SCOPE_DRAFT_VOUCHERS,
    "draft_journal_voucher": SCOPE_DRAFT_VOUCHERS,
    "get_draft_status": SCOPE_DRAFT_VOUCHERS,
    "cancel_draft": SCOPE_DRAFT_VOUCHERS,
    "approve_voucher": SCOPE_APPROVE_VOUCHERS,
}


class ScopeDeniedError(Exception):
    """Raised when an actor lacks the required scope to execute a tool or access a resource."""

    def __init__(self, message: str, required_scope: str, granted_scopes: list[str]):
        super().__init__(message)
        self.code = "SCOPE_DENIED"
        self.required_scope = required_scope
        self.granted_scopes = granted_scopes


def check_tool_permission(claims: TokenClaims, tool_name: str) -> None:
    """Verify that token claims satisfy the required scope for a given MCP tool.

    Raises:
        ScopeDeniedError: If claims.scopes does not include the required scope.
    """
    required_scope = TOOL_SCOPE_REQUIREMENTS.get(tool_name)
    if not required_scope:
        # If an unknown tool is invoked, deny by default
        raise ScopeDeniedError(
            f"Access Denied: Unrecognized or unregistered tool '{tool_name}'.",
            required_scope="unknown",
            granted_scopes=claims.scopes,
        )

    # Human-only scope guard
    if required_scope == SCOPE_APPROVE_VOUCHERS and claims.client_type != "human_user":
        raise ScopeDeniedError(
            "Access Denied: Approvals can only be performed by authenticated human users, "
            "never by AI assistants or automated client tokens.",
            required_scope=required_scope,
            granted_scopes=claims.scopes,
        )

    if required_scope not in claims.scopes:
        raise ScopeDeniedError(
            f"SCOPE_DENIED: Executing tool '{tool_name}' requires scope '{required_scope}', "
            f"but granted scopes are {claims.scopes}.",
            required_scope=required_scope,
            granted_scopes=claims.scopes,
        )
