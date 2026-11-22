"""Tally Prime HTTP/XML Bridge Adapter Client.

Manages connection to local Tally XML interface (default localhost:9000).
Enforces:
1. Template allow-listing (rejects raw or unknown XML).
2. Safe HTTP POST with timeout and error handling (returns TALLY_UNAVAILABLE when down).
3. Exact decimal parsing and untrusted text sanitization.
4. Support for custom transports (e.g. simulated in-memory transport for tests).
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
import httpx

from bridge.templates.allowlist import (
    render_template,
    TEMPLATE_COMPANY_INFO,
    TEMPLATE_LIST_LEDGERS,
    TEMPLATE_PARTY_LEDGER,
    TEMPLATE_RECEIVABLES_AGEING,
    TEMPLATE_SEARCH_VOUCHERS,
    TEMPLATE_STOCK_SUMMARY,
)
from bridge.tally_adapter.xml_parser import (
    parse_company_info,
    parse_ledgers,
    parse_party_ledger,
    parse_receivables_ageing,
    parse_stock_summary,
)


class TallyConnectionError(Exception):
    """Raised when Tally instance is offline, unreachable, or returns an error."""
    pass


class TallyAdapterClient:
    """High-level client for communicating with local Tally XML endpoint."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        company_name: str = "Surat Textile Traders Pvt Ltd",
        timeout_seconds: float = 10.0,
        transport: Optional[httpx.BaseTransport] = None,
        endpoint: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        if endpoint:
            self.endpoint = endpoint
            # Extract host and port if feasible
            cleaned = endpoint.replace("http://", "").replace("https://", "").rstrip("/")
            if ":" in cleaned:
                self.host, port_str = cleaned.split(":", 1)
                self.port = int(port_str) if port_str.isdigit() else 9000
            else:
                self.host = cleaned
                self.port = 9000
        else:
            self.host = host
            self.port = port
            self.endpoint = f"http://{host}:{port}"

        self.company_name = company_name
        self.timeout = timeout if timeout is not None else timeout_seconds
        self.transport = transport

    def _execute_template(self, template_id: str, params: Dict[str, Any]) -> str:
        """Render allow-listed template and POST to Tally instance."""
        params["company_name"] = self.company_name
        xml_payload = render_template(template_id, params)

        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
                response = client.post(
                    self.endpoint,
                    content=xml_payload.encode("utf-8"),
                    headers={"Content-Type": "text/xml; charset=utf-8"},
                )
                if response.status_code != 200:
                    raise TallyConnectionError(
                        f"Tally returned HTTP {response.status_code}: {response.text[:200]}"
                    )
                return response.text
        except httpx.RequestError as e:
            raise TallyConnectionError(
                f"TALLY_UNAVAILABLE: Could not connect to Tally on {self.endpoint}. "
                f"Ensure Tally is running and port {self.port} is accessible."
            ) from e

    def get_company_info(self) -> Dict[str, Any]:
        """Fetch company identity, financial year, and base currency."""
        xml_resp = self._execute_template(TEMPLATE_COMPANY_INFO, {})
        return parse_company_info(xml_resp)

    def list_ledgers(self, group_filter: str = "") -> List[Dict[str, Any]]:
        """List ledgers from Chart of Accounts, optionally filtered by group."""
        xml_resp = self._execute_template(TEMPLATE_LIST_LEDGERS, {"group_filter": group_filter})
        return parse_ledgers(xml_resp)

    def get_party_ledger(
        self, party_name: str, from_date: str, to_date: str
    ) -> Dict[str, Any]:
        """Fetch party account statement with debit, credit, and running balance."""
        xml_resp = self._execute_template(
            TEMPLATE_PARTY_LEDGER,
            {"party_name": party_name, "from_date": from_date, "to_date": to_date},
        )
        return parse_party_ledger(xml_resp)

    def get_receivables_ageing(
        self,
        as_on_date: str,
        buckets: Optional[List[int]] = None,
        min_amount: Optional[Decimal] = None,
        top_n: int = 20,
    ) -> Dict[str, Any]:
        """Fetch outstanding bills and compute aging buckets."""
        xml_resp = self._execute_template(
            TEMPLATE_RECEIVABLES_AGEING, {"as_on_date": as_on_date}
        )
        return parse_receivables_ageing(xml_resp, as_on_date, buckets, min_amount, top_n)

    def get_stock_summary(self, as_on_date: str) -> List[Dict[str, Any]]:
        """Fetch stock inventory summary."""
        xml_resp = self._execute_template(TEMPLATE_STOCK_SUMMARY, {"as_on_date": as_on_date})
        return parse_stock_summary(xml_resp)


# Alias for backward and forward compatibility
TallyClient = TallyAdapterClient

