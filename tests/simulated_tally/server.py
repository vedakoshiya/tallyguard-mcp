"""Simulated Tally Prime HTTP/XML Server and In-Memory Transport for Testing.

Emulates Tally Prime's local XML-over-HTTP endpoint.
Processes allow-listed Tally XML requests and returns authentic Tally XML responses
backed by the Surat Textile Traders reference fixture.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from typing import Optional
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
import httpx

from tests.fixtures.company_data import (
    COMPANY_METADATA,
    CHART_OF_ACCOUNTS,
    SAMPLE_VOUCHERS,
    RECEIVABLES_BILLS,
    STOCK_ITEMS,
)


def dispatch_simulated_tally_xml(xml_text: str) -> str:
    """Core logic: Parse incoming Tally XML request and return Tally XML response."""
    try:
        root = ET.fromstring(xml_text)
        req_elem = root.find(".//TALLYREQUEST")
        req_type = req_elem.text.strip() if req_elem is not None and req_elem.text else ""

        if req_type == "Import Data":
            # Emulate successful voucher import
            vch_type_elem = root.find(".//VOUCHERTYPENAME")
            vch_type = vch_type_elem.text.strip() if vch_type_elem is not None and vch_type_elem.text else "VCH"
            prefix = (
                "REC"
                if "receipt" in vch_type.lower()
                else "SAL"
                if "sales" in vch_type.lower()
                else "PAY"
                if "payment" in vch_type.lower()
                else "JRN"
                if "journal" in vch_type.lower()
                else "VCH"
            )
            return f"""<RESPONSE>
  <CREATED>1</CREATED>
  <ALTERED>0</ALTERED>
  <ERRORS>0</ERRORS>
  <VOUCHERNUMBER>{prefix}-2026-88</VOUCHERNUMBER>
</RESPONSE>"""

        report_name_elem = root.find(".//REPORTNAME")
        report_name = (
            report_name_elem.text.strip()
            if report_name_elem is not None and report_name_elem.text
            else ""
        )
    except Exception:
        return "<RESPONSE><STATUS>ERROR</STATUS><MESSAGE>Malformed XML</MESSAGE></RESPONSE>"

    if report_name == "Company Details":
        return _build_company_info_response()
    elif report_name == "List of Accounts":
        group_elem = root.find(".//GROUP")
        group_filter = (
            group_elem.text.strip()
            if group_elem is not None and group_elem.text
            else ""
        )
        return _build_ledgers_response(group_filter)
    elif report_name == "Ledger Vouchers":
        ledger_name_elem = root.find(".//LEDGERNAME")
        ledger_name = (
            ledger_name_elem.text.strip()
            if ledger_name_elem is not None and ledger_name_elem.text
            else ""
        )
        return _build_party_ledger_response(ledger_name)
    elif report_name == "Bills Receivable":
        return _build_bills_receivable_response()
    elif report_name == "Day Book":
        return _build_day_book_response()
    elif report_name == "Stock Summary":
        return _build_stock_summary_response()

    return f"<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA>Unknown report: {xml_escape(report_name)}</DATA></BODY></ENVELOPE>"


def _build_company_info_response() -> str:
    m = COMPANY_METADATA
    return f"""<ENVELOPE>
  <HEADER>
    <STATUS>1</STATUS>
  </HEADER>
  <BODY>
    <DATA>
      <COMPANYNAME>{xml_escape(str(m["name"]))}</COMPANYNAME>
      <STARTINGFROM>{xml_escape(str(m["financial_year_from"]))}</STARTINGFROM>
      <ENDINGAT>{xml_escape(str(m["financial_year_to"]))}</ENDINGAT>
      <BOOKSFROM>{xml_escape(str(m["books_from"]))}</BOOKSFROM>
      <BASECURRENCY>{xml_escape(str(m["base_currency"]))}</BASECURRENCY>
      <CURRENCYSYMBOL>{xml_escape(str(m["currency_symbol"]))}</CURRENCYSYMBOL>
      <GSTIN>{xml_escape(str(m["gstin"]))}</GSTIN>
      <ADDRESS>{xml_escape(str(m["address"]))}</ADDRESS>
    </DATA>
  </BODY>
</ENVELOPE>"""


def _build_ledgers_response(group_filter: str = "") -> str:
    items = []
    for l in CHART_OF_ACCOUNTS:
        if group_filter and l["parent"].lower() != group_filter.lower():
            continue
        dr_cr_op = "Dr" if l["is_debit"] else "Cr"
        dr_cr_cl = "Dr" if l["is_debit"] else "Cr"
        name_esc = xml_escape(str(l["name"]))
        parent_esc = xml_escape(str(l["parent"]))
        items.append(f"""      <LEDGER NAME="{name_esc}">
        <NAME>{name_esc}</NAME>
        <PARENT>{parent_esc}</PARENT>
        <OPENINGBALANCE>{l['opening_balance']:.2f} {dr_cr_op}</OPENINGBALANCE>
        <CLOSINGBALANCE>{l['closing_balance']:.2f} {dr_cr_cl}</CLOSINGBALANCE>
      </LEDGER>""")

    ledgers_xml = "\n".join(items)
    return f"""<ENVELOPE>
  <HEADER>
    <STATUS>1</STATUS>
  </HEADER>
  <BODY>
    <DATA>
      <COLLECTION NAME="Ledgers">
{ledgers_xml}
      </COLLECTION>
    </DATA>
  </BODY>
</ENVELOPE>"""


def _build_party_ledger_response(party_name: str) -> str:
    ledger = next((l for l in CHART_OF_ACCOUNTS if l["name"].lower() == party_name.lower()), None)
    if not ledger:
        return f"""<ENVELOPE><BODY><DATA><MESSAGE>Ledger '{xml_escape(party_name)}' not found</MESSAGE></DATA></BODY></ENVELOPE>"""

    party_vouchers = []
    running = ledger["opening_balance"]
    for v in SAMPLE_VOUCHERS:
        for line in v["lines"]:
            if line["ledger"].lower() == party_name.lower():
                is_dr = line["is_debit"]
                amt = line["amount"]
                if is_dr:
                    running += amt
                else:
                    running -= amt
                party_vouchers.append(f"""        <VOUCHER>
          <VOUCHERNUMBER>{xml_escape(str(v['voucher_no']))}</VOUCHERNUMBER>
          <DATE>{xml_escape(str(v['date']))}</DATE>
          <VOUCHERTYPENAME>{xml_escape(str(v['voucher_type']))}</VOUCHERTYPENAME>
          <AMOUNT>{amt:.2f}</AMOUNT>
          <ISDEBIT>{'Yes' if is_dr else 'No'}</ISDEBIT>
          <RUNNINGBALANCE>{running:.2f}</RUNNINGBALANCE>
          <NARRATION>{xml_escape(str(v['narration']))}</NARRATION>
        </VOUCHER>""")

    vouchers_xml = "\n".join(party_vouchers)
    return f"""<ENVELOPE>
  <HEADER><STATUS>1</STATUS></HEADER>
  <BODY>
    <DATA>
      <LEDGERNAME>{xml_escape(str(ledger['name']))}</LEDGERNAME>
      <OPENINGBALANCE>{ledger['opening_balance']:.2f}</OPENINGBALANCE>
      <CLOSINGBALANCE>{ledger['closing_balance']:.2f}</CLOSINGBALANCE>
      <ALLLEDGERENTRIES>
{vouchers_xml}
      </ALLLEDGERENTRIES>
    </DATA>
  </BODY>
</ENVELOPE>"""


def _build_bills_receivable_response() -> str:
    bills = []
    for b in RECEIVABLES_BILLS:
        bills.append(f"""      <BILL>
        <BILLNO>{xml_escape(str(b['bill_no']))}</BILLNO>
        <PARTYNAME>{xml_escape(str(b['party']))}</PARTYNAME>
        <BILLDATE>{xml_escape(str(b['bill_date']))}</BILLDATE>
        <DUEDATE>{xml_escape(str(b['due_date']))}</DUEDATE>
        <ORIGINALAMOUNT>{b['original_amount']:.2f}</ORIGINALAMOUNT>
        <PENDINGAMOUNT>{b['pending_amount']:.2f}</PENDINGAMOUNT>
      </BILL>""")

    bills_xml = "\n".join(bills)
    return f"""<ENVELOPE>
  <HEADER><STATUS>1</STATUS></HEADER>
  <BODY>
    <DATA>
      <COLLECTION NAME="BillsReceivable">
{bills_xml}
      </COLLECTION>
    </DATA>
  </BODY>
</ENVELOPE>"""


def _build_day_book_response() -> str:
    vouchers = []
    for v in SAMPLE_VOUCHERS:
        vouchers.append(f"""      <VOUCHER>
        <VOUCHERNUMBER>{xml_escape(str(v['voucher_no']))}</VOUCHERNUMBER>
        <DATE>{xml_escape(str(v['date']))}</DATE>
        <VOUCHERTYPENAME>{xml_escape(str(v['voucher_type']))}</VOUCHERTYPENAME>
        <PARTYNAME>{xml_escape(str(v['party']))}</PARTYNAME>
        <AMOUNT>{v['amount']:.2f}</AMOUNT>
        <NARRATION>{xml_escape(str(v['narration']))}</NARRATION>
      </VOUCHER>""")

    vouchers_xml = "\n".join(vouchers)
    return f"""<ENVELOPE>
  <HEADER><STATUS>1</STATUS></HEADER>
  <BODY>
    <DATA>
      <COLLECTION NAME="DayBook">
{vouchers_xml}
      </COLLECTION>
    </DATA>
  </BODY>
</ENVELOPE>"""


def _build_stock_summary_response() -> str:
    items = []
    for s in STOCK_ITEMS:
        items.append(f"""      <STOCKITEM>
        <NAME>{xml_escape(str(s['name']))}</NAME>
        <GROUP>{xml_escape(str(s['group']))}</GROUP>
        <CLOSINGQTY>{s['closing_qty']:.2f}</CLOSINGQTY>
        <UOM>{xml_escape(str(s['uom']))}</UOM>
        <RATE>{s['rate']:.2f}</RATE>
        <CLOSINGVALUE>{s['closing_value']:.2f}</CLOSINGVALUE>
      </STOCKITEM>""")

    stock_xml = "\n".join(items)
    return f"""<ENVELOPE>
  <HEADER><STATUS>1</STATUS></HEADER>
  <BODY>
    <DATA>
      <COLLECTION NAME="StockSummary">
{stock_xml}
      </COLLECTION>
    </DATA>
  </BODY>
</ENVELOPE>"""


def create_simulated_tally_transport() -> httpx.MockTransport:
    """Create an in-memory httpx.MockTransport emulating Tally Prime XML HTTP server."""
    def handler(request: httpx.Request) -> httpx.Response:
        xml_request = request.content.decode("utf-8")
        xml_response = dispatch_simulated_tally_xml(xml_request)
        return httpx.Response(
            status_code=200,
            content=xml_response.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8", "Server": "TallyPrime/Simulated"},
        )
    return httpx.MockTransport(handler)


class SimulatedTallyHandler(BaseHTTPRequestHandler):
    """HTTP request handler for running a real local socket server."""

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8")
        response_xml = dispatch_simulated_tally_xml(post_data)

        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Server", "TallyPrime/Simulated")
        self.end_headers()
        self.wfile.write(response_xml.encode("utf-8"))


class SimulatedTallyServer:
    """Manager to run the simulated Tally HTTP server in a thread when TCP socket is desired."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9000):
        self.host = host
        self.port = port
        self.httpd: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self.httpd = HTTPServer((self.host, self.port), SimulatedTallyHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
