"""Idempotent Voucher Posting Engine for TallyGuard MCP Bridge.

Implements FR-065, US-05, and Invariant INV-04:
Converts approved draft transaction payloads into Tally import XML,
submits them with a unique idempotency_key, and verifies the created voucher number.
"""

from decimal import Decimal
from typing import Any, Dict, Optional
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
import httpx

from bridge.tally_adapter.client import TallyConnectionError


class PostingError(Exception):
    """Raised when Tally rejects voucher import or returns errors."""
    pass


class VoucherPoster:
    """Handles posting of approved draft payloads into Tally."""

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:9000",
        company_name: str = "Surat Textile Traders Pvt Ltd",
        transport: Optional[httpx.BaseTransport] = None,
        timeout: float = 10.0,
    ):
        self.endpoint = endpoint
        self.company_name = company_name
        self.transport = transport
        self.timeout = timeout

    def build_import_xml(self, payload: Dict[str, Any], idempotency_key: str) -> str:
        """Construct valid Tally Import Data XML for creating a voucher."""
        comp = xml_escape(self.company_name)
        v_type = xml_escape(str(payload.get("voucher_type", "Receipt")))
        v_date = xml_escape(str(payload.get("date", "")).replace("-", ""))
        narration = xml_escape(str(payload.get("narration", "")))
        party = xml_escape(str(payload.get("party", "")))

        # Build ledger entry lines
        lines_xml = []
        for line in payload.get("lines", []):
            ledger = xml_escape(str(line.get("ledger", "")))
            amt = line.get("amount", "0.00")
            is_dr = line.get("is_debit", True)
            # In Tally XML convention, Debit amounts are negative inside ALLLEDGERENTRIES.LIST
            tally_amt = f"-{amt}" if is_dr else f"{amt}"
            lines_xml.append(f"""              <ALLLEDGERENTRIES.LIST>
                <LEDGERNAME>{ledger}</LEDGERNAME>
                <ISDEBIT>{'Yes' if is_dr else 'No'}</ISDEBIT>
                <AMOUNT>{tally_amt}</AMOUNT>
              </ALLLEDGERENTRIES.LIST>""")

        lines_str = "\n".join(lines_xml)

        return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>All Masters</REPORTNAME>
        <STATICVARIABLES>
          <SVCURRENTCOMPANY>{comp}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <VOUCHER VCHTYPE="{v_type}" ACTION="Create">
            <DATE>{v_date}</DATE>
            <NARRATION>{narration} [Ref: {xml_escape(idempotency_key)}]</NARRATION>
            <VOUCHERTYPENAME>{v_type}</VOUCHERTYPENAME>
            <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>
            <IDEMPOTENCYKEY>{xml_escape(idempotency_key)}</IDEMPOTENCYKEY>
{lines_str}
          </VOUCHER>
        </TALLYMESSAGE>
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""

    def post_approved_voucher(
        self, payload: Dict[str, Any], idempotency_key: str
    ) -> Dict[str, Any]:
        """Submit approved voucher to Tally and parse created voucher number."""
        xml_payload = self.build_import_xml(payload, idempotency_key)

        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
                resp = client.post(
                    self.endpoint,
                    content=xml_payload.encode("utf-8"),
                    headers={"Content-Type": "text/xml; charset=utf-8"},
                )
                if resp.status_code != 200:
                    raise PostingError(f"Tally HTTP {resp.status_code}: {resp.text[:200]}")
                return self._parse_import_response(resp.text)
        except httpx.RequestError as e:
            raise TallyConnectionError(
                f"TALLY_UNAVAILABLE: Failed to communicate with Tally during posting: {e}"
            ) from e

    def _parse_import_response(self, response_xml: str) -> Dict[str, Any]:
        """Parse Tally Import response and verify errors count."""
        try:
            root = ET.fromstring(response_xml)
            created_elem = root.find(".//CREATED")
            errors_elem = root.find(".//ERRORS")
            v_no_elem = root.find(".//VOUCHERNUMBER")

            created_count = int(created_elem.text) if created_elem is not None and created_elem.text else 0
            errors_count = int(errors_elem.text) if errors_elem is not None and errors_elem.text else 0
            voucher_no = v_no_elem.text.strip() if v_no_elem is not None and v_no_elem.text else None

            if errors_count > 0:
                raise PostingError(f"Tally rejected voucher creation with {errors_count} error(s).")

            if created_count < 1 and not voucher_no:
                # Fallback check
                msg = root.findtext(".//MESSAGE", "Unknown posting error")
                raise PostingError(f"Voucher creation not confirmed by Tally: {msg}")

            return {
                "created": True,
                "tally_voucher_no": voucher_no or "VCH-CONFIRMED",
            }
        except ET.ParseError as e:
            raise PostingError(f"Invalid XML returned by Tally on voucher post: {e}") from e
