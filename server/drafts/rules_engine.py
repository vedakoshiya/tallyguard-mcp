"""Financial Anomaly Detection Rules Engine for TallyGuard MCP Drafts.

Implements FR-062, FR-063, and STRIDE prompt-injection mitigation.
Evaluates proposed drafts against business rules before approval:
1. High amount threshold checks (flags high-value transactions).
2. Second-approver requirements for high-risk amounts.
3. New / unrecognized beneficiary detection (anti-injection defense).
4. Weekend and backdated entry detection.
5. Suspected duplicate voucher detection (same party, amount, and date).
6. Ledger scope compliance.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from bridge.tally_adapter.decimal_math import ensure_decimal


@dataclass
class AnomalyReport:
    """Evaluation output from rules engine."""

    flags: list[str]
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    requires_second_approver: bool
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "flags": self.flags,
            "risk_level": self.risk_level,
            "requires_second_approver": self.requires_second_approver,
            "details": self.details,
        }


class AnomalyRulesEngine:
    """Evaluates drafts against tenant approval policies and financial anomaly rules."""

    def __init__(
        self,
        single_amount_threshold: Decimal = Decimal("50000.00"),
        second_approver_threshold: Decimal = Decimal("200000.00"),
        max_backdated_days: int = 30,
    ):
        self.single_amount_threshold = single_amount_threshold
        self.second_approver_threshold = second_approver_threshold
        self.max_backdated_days = max_backdated_days

    def evaluate_draft(
        self,
        party_name: str,
        total_amount: Decimal,
        voucher_date_str: str,
        known_ledgers: set[str] | None = None,
        existing_vouchers: list[dict[str, Any]] | None = None,
        user_allowlist: list[str] | None = None,
    ) -> AnomalyReport:
        """Run all anomaly checks on a proposed voucher draft."""
        flags: list[str] = []
        details: list[str] = []
        requires_second_approver = False

        amt = ensure_decimal(total_amount)

        # 1. Amount Threshold Rules (FR-062, FR-063)
        if amt >= self.second_approver_threshold:
            flags.append("amount_requires_second_approver")
            requires_second_approver = True
            details.append(
                f"Amount ₹{amt:.2f} exceeds high-risk threshold of ₹{self.second_approver_threshold:.2f}."
            )
        elif amt >= self.single_amount_threshold:
            flags.append("amount_above_threshold")
            details.append(
                f"Amount ₹{amt:.2f} exceeds standard approval threshold of ₹{self.single_amount_threshold:.2f}."
            )

        # 2. New Party Reference Rule (Anti-Injection / Anti-Exfiltration)
        if known_ledgers is not None:
            normalized_known = {name.strip().lower() for name in known_ledgers}
            if party_name.strip().lower() not in normalized_known:
                flags.append("new_party_reference")
                details.append(f"Party '{party_name}' is not in existing Chart of Accounts.")

        # 3. Date Rules: Backdated and Weekend entries
        try:
            v_date = datetime.strptime(voucher_date_str, "%Y-%m-%d").date()
            today = date.today()

            # Weekend check (Sunday = 6)
            if v_date.weekday() == 6:
                flags.append("weekend_entry")
                details.append(f"Voucher date {voucher_date_str} falls on a Sunday.")

            # Backdated check
            if (today - v_date).days > self.max_backdated_days:
                flags.append("backdated_entry")
                details.append(
                    f"Voucher date {voucher_date_str} is older than {self.max_backdated_days} days."
                )
        except ValueError:
            flags.append("malformed_date")
            details.append(f"Could not parse date string: {voucher_date_str}")

        # 4. Duplicate Voucher Detection Rule
        if existing_vouchers:
            party_norm = party_name.strip().lower()
            for v in existing_vouchers:
                v_party = str(v.get("party", "")).strip().lower()
                v_date_str = str(v.get("date", ""))
                v_amt = ensure_decimal(v.get("amount", "0.00"))

                if v_party == party_norm and v_amt == amt and v_date_str == voucher_date_str:
                    flags.append("suspected_duplicate_voucher")
                    details.append(
                        f"Suspected duplicate: An existing voucher for '{party_name}' with amount "
                        f"₹{amt:.2f} on {voucher_date_str} already exists."
                    )
                    break

        # 5. User Allow-List Scope Compliance
        if user_allowlist is not None:
            normalized_allowlist = {a.strip().lower() for a in user_allowlist}
            if party_name.strip().lower() not in normalized_allowlist:
                flags.append("ledger_outside_scope")
                details.append(f"Party '{party_name}' is not in user's permitted allow-list.")

        # Determine overall risk level
        if "amount_requires_second_approver" in flags or "suspected_duplicate_voucher" in flags or "ledger_outside_scope" in flags:
            risk_level = "HIGH"
        elif "amount_above_threshold" in flags or "new_party_reference" in flags:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return AnomalyReport(
            flags=flags,
            risk_level=risk_level,
            requires_second_approver=requires_second_approver,
            details=details,
        )
