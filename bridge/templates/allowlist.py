"""Template Allow-List Engine for TallyGuard MCP Bridge.

Satisfies FR-072 & STRIDE mitigation against arbitrary XML injection.
The bridge agent strictly accepts vetted `template_id` and parameter dictionaries;
it NEVER executes arbitrary XML received from external networks.
"""

from typing import Any, Dict
import html

# Template IDs
TEMPLATE_COMPANY_INFO = "get_company_info"
TEMPLATE_LIST_LEDGERS = "list_ledgers"
TEMPLATE_PARTY_LEDGER = "get_party_ledger"
TEMPLATE_RECEIVABLES_AGEING = "get_receivables_ageing"
TEMPLATE_PAYABLES_AGEING = "get_payables_ageing"
TEMPLATE_SEARCH_VOUCHERS = "search_vouchers"
TEMPLATE_STOCK_SUMMARY = "get_stock_summary"
TEMPLATE_GST_SUMMARY = "get_gst_summary"
TEMPLATE_TRIAL_BALANCE = "get_trial_balance"

ALLOWED_TEMPLATE_IDS = {
    TEMPLATE_COMPANY_INFO,
    TEMPLATE_LIST_LEDGERS,
    TEMPLATE_PARTY_LEDGER,
    TEMPLATE_RECEIVABLES_AGEING,
    TEMPLATE_PAYABLES_AGEING,
    TEMPLATE_SEARCH_VOUCHERS,
    TEMPLATE_STOCK_SUMMARY,
    TEMPLATE_GST_SUMMARY,
    TEMPLATE_TRIAL_BALANCE,
}


def _xml_escape(val: Any) -> str:
    """Safely escape values before interpolating into XML templates."""
    if val is None:
        return ""
    return html.escape(str(val), quote=True)


def build_company_info_xml(company_name: str) -> str:
    """Build XML to query current active company information."""
    comp = _xml_escape(company_name)
    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <EXPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Company Details</REPORTNAME>
        <STATICVARIABLES>
          <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
          <SVCURRENTCOMPANY>{comp}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
    </EXPORTDATA>
  </BODY>
</ENVELOPE>"""


def build_list_ledgers_xml(company_name: str, group_filter: str = "") -> str:
    """Build XML to fetch chart of accounts / ledgers."""
    comp = _xml_escape(company_name)
    group_var = f"<GROUP>{_xml_escape(group_filter)}</GROUP>" if group_filter else ""
    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <EXPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>List of Accounts</REPORTNAME>
        <STATICVARIABLES>
          <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
          <SVCURRENTCOMPANY>{comp}</SVCURRENTCOMPANY>
          <ACCOUNTTYPE>All Ledgers</ACCOUNTTYPE>
          {group_var}
        </STATICVARIABLES>
      </REQUESTDESC>
    </EXPORTDATA>
  </BODY>
</ENVELOPE>"""


def build_party_ledger_xml(
    company_name: str, party_name: str, from_date: str, to_date: str
) -> str:
    """Build XML to fetch account entries and running balance for a specific party."""
    comp = _xml_escape(company_name)
    party = _xml_escape(party_name)
    f_date = _xml_escape(from_date.replace("-", ""))
    t_date = _xml_escape(to_date.replace("-", ""))

    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <EXPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Ledger Vouchers</REPORTNAME>
        <STATICVARIABLES>
          <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
          <SVCURRENTCOMPANY>{comp}</SVCURRENTCOMPANY>
          <LEDGERNAME>{party}</LEDGERNAME>
          <SVFROMDATE>{f_date}</SVFROMDATE>
          <SVTODATE>{t_date}</SVTODATE>
        </STATICVARIABLES>
      </REQUESTDESC>
    </EXPORTDATA>
  </BODY>
</ENVELOPE>"""


def build_bills_ageing_xml(
    company_name: str, report_type: str, as_on_date: str
) -> str:
    """Build XML to query outstanding receivables or payables bills."""
    comp = _xml_escape(company_name)
    a_date = _xml_escape(as_on_date.replace("-", ""))
    report_name = "Bills Receivable" if report_type == "receivables" else "Bills Payable"

    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <EXPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>{report_name}</REPORTNAME>
        <STATICVARIABLES>
          <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
          <SVCURRENTCOMPANY>{comp}</SVCURRENTCOMPANY>
          <SVTODATE>{a_date}</SVTODATE>
        </STATICVARIABLES>
      </REQUESTDESC>
    </EXPORTDATA>
  </BODY>
</ENVELOPE>"""


def build_search_vouchers_xml(
    company_name: str,
    from_date: str,
    to_date: str,
    voucher_type: str = "",
) -> str:
    """Build XML to search transactions in Day Book."""
    comp = _xml_escape(company_name)
    f_date = _xml_escape(from_date.replace("-", ""))
    t_date = _xml_escape(to_date.replace("-", ""))
    v_type = f"<VOUCHERTYPENAME>{_xml_escape(voucher_type)}</VOUCHERTYPENAME>" if voucher_type else ""

    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <EXPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Day Book</REPORTNAME>
        <STATICVARIABLES>
          <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
          <SVCURRENTCOMPANY>{comp}</SVCURRENTCOMPANY>
          <SVFROMDATE>{f_date}</SVFROMDATE>
          <SVTODATE>{t_date}</SVTODATE>
          {v_type}
        </STATICVARIABLES>
      </REQUESTDESC>
    </EXPORTDATA>
  </BODY>
</ENVELOPE>"""


def build_stock_summary_xml(company_name: str, as_on_date: str) -> str:
    """Build XML for stock items and valuations."""
    comp = _xml_escape(company_name)
    a_date = _xml_escape(as_on_date.replace("-", ""))
    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <EXPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Stock Summary</REPORTNAME>
        <STATICVARIABLES>
          <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
          <SVCURRENTCOMPANY>{comp}</SVCURRENTCOMPANY>
          <SVTODATE>{a_date}</SVTODATE>
        </STATICVARIABLES>
      </REQUESTDESC>
    </EXPORTDATA>
  </BODY>
</ENVELOPE>"""


def render_template(template_id: str, params: Dict[str, Any]) -> str:
    """Validate template_id against allow-list and render XML safely.

    Raises:
        ValueError: If template_id is not in ALLOWED_TEMPLATE_IDS or required params missing.
    """
    if template_id not in ALLOWED_TEMPLATE_IDS:
        raise ValueError(
            f"Security Exception: Template ID '{template_id}' is not in the bridge allow-list. "
            f"Arbitrary XML execution is prohibited."
        )

    company_name = params.get("company_name", "")

    if template_id == TEMPLATE_COMPANY_INFO:
        return build_company_info_xml(company_name)
    elif template_id == TEMPLATE_LIST_LEDGERS:
        return build_list_ledgers_xml(company_name, params.get("group_filter", ""))
    elif template_id == TEMPLATE_PARTY_LEDGER:
        return build_party_ledger_xml(
            company_name,
            params.get("party_name", ""),
            params.get("from_date", ""),
            params.get("to_date", ""),
        )
    elif template_id == TEMPLATE_RECEIVABLES_AGEING:
        return build_bills_ageing_xml(company_name, "receivables", params.get("as_on_date", ""))
    elif template_id == TEMPLATE_PAYABLES_AGEING:
        return build_bills_ageing_xml(company_name, "payables", params.get("as_on_date", ""))
    elif template_id == TEMPLATE_SEARCH_VOUCHERS:
        return build_search_vouchers_xml(
            company_name,
            params.get("from_date", ""),
            params.get("to_date", ""),
            params.get("voucher_type", ""),
        )
    elif template_id == TEMPLATE_STOCK_SUMMARY:
        return build_stock_summary_xml(company_name, params.get("as_on_date", ""))

    raise ValueError(f"Unhandled allow-listed template: {template_id}")
