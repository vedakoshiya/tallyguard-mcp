# TallyGuard MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![MCP Standard](https://img.shields.io/badge/MCP-v1.2%2B-green.svg)](https://modelcontextprotocol.io)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**A Governed Model Context Protocol (MCP) Server for Safe, Read-Reconciled, and Draft-Only AI Access to Tally Accounting Data.**

---

## Overview

Tally Prime and Tally ERP 9 serve as the system of record for hundreds of thousands of Indian businesses. However, connecting modern LLMs and AI assistants (such as Claude Desktop or custom autonomous agents) directly to accounting systems poses immense risks: unauthorized data mutations, lack of approval workflows, and prompt injection attacks embedded inside ledger names or transaction narrations.

**TallyGuard MCP** provides an enterprise-grade governance boundary between AI clients and Tally:
1. **Paisa-Exact Reconciliation**: All read queries calculate and reconcile numbers to the exact paisa using decimal arithmetic (zero floating-point math).
2. **Draft-Only Writes**: AI assistants can **never** post or alter vouchers in Tally. Write tools strictly generate proposed **drafts** stored externally.
3. **Out-of-Band Human Approval**: Posting vouchers to Tally requires human authentication and approval. The approval channel is decoupled from the MCP AI context.
4. **Prompt Injection Containment**: Free text fields from Tally (narrations, remarks, party names) are sanitized and wrapped in structured `untrusted_text` containers.
5. **Zero Inbound Ports**: The on-premises bridge agent initiates an outbound-only TLS connection. No firewall pinholes or port forwarding required.
6. **Immutable Audit Trails**: Every request, parameter hash, and state transition is cryptographically chained in an append-only audit log.

---

## Architecture

```
 AI Assistant (Claude Desktop / Agent)
        │
        ▼ (MCP Protocol via stdio or Streamable HTTP)
 [TallyGuard MCP Server]
   ├── Auth & Scopes (read:reports, draft:vouchers, etc.)
   ├── Sanitizer (Untrusted text isolation)
   ├── Anomaly Rules Engine (Thresholds, new parties, duplicates)
   └── Cryptographic Audit Trail (Append-only hash chain)
        │
        ▼ (Internal Relay / Outbound TLS)
 [On-Premises Windows Bridge Agent]
   ├── Template Allow-List (Rejects arbitrary XML)
   └── Tally XML Adapter (Exact Decimal Math)
        │
        ▼ (Localhost XML/HTTP - Default: 9000)
 [Tally Prime / ERP 9 Instance]
```

---

## MCP Surface

### Read Tools (Side-Effect Free)
- `get_company_info`: Retrieve active company name, financial year, and currency.
- `list_ledgers`: List ledgers with group/prefix filters and cursor pagination.
- `get_party_ledger`: Detailed account statement with opening, entries, running, and closing balance.
- `get_receivables_ageing`: Outstanding receivables categorized in aging buckets (0–30, 31–60, 61–90, 90+ days).
- `get_payables_ageing`: Outstanding payables categorized in aging buckets.
- `search_vouchers`: Search transaction vouchers with multi-field filters and stable pagination.
- `get_stock_summary`: Closing stock quantities and valuations.
- `get_gst_summary`: Summary of inward and outward tax totals for a period.
- `get_trial_balance`, `get_profit_and_loss`, `get_balance_sheet`: Core financial statements.

### Write Tools (Draft-Only)
- `draft_receipt_voucher`: Prepare a receipt voucher draft.
- `draft_sales_voucher`: Prepare a sales voucher draft with line items, rates, and taxes.
- `draft_payment_voucher` & `draft_journal_voucher`: Prepare payment or journal voucher drafts.
- `get_draft_status`: Query the status and approval URL for an existing draft.
- `cancel_draft`: Cancel a pending draft created by the current user.

---

## Quickstart

### Prerequisites
- Python 3.11+
- Tally Prime or Tally ERP 9 with XML/ODBC interface enabled (default port 9000).

### 1. Installation
Clone the repository and set up a virtual environment:
```bash
git clone https://github.com/vedakoshiya/tallyguard-mcp.git
cd tallyguard-mcp
python -m venv .venv
# On Windows:
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

pip install -e ".[dev]"
```

### 2. Configuration
Copy the sample environment file:
```bash
cp .env.example .env
```
Update `.env` with your local settings (ensure `TALLY_HOST` and `TALLY_PORT` point to your Tally instance).

### 3. Running with Claude Desktop (stdio mode)
Add TallyGuard MCP to your Claude Desktop configuration file (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "tallyguard": {
      "command": "python",
      "args": ["-m", "server.main"],
      "cwd": "C:\\path\\to\\tallyguard-mcp",
      "env": {
        "MCP_TRANSPORT": "stdio",
        "TALLY_HOST": "127.0.0.1",
        "TALLY_PORT": "9000"
      }
    }
  }
}
```

---

## Repository Structure

```text
tallyguard-mcp/
├── server/                       # MCP server, auth, sanitizer, audit engine
│   ├── mcp/                      # Tools, resources, prompts, schemas
│   ├── auth/                     # OAuth 2.1 & scope management
│   ├── drafts/                   # Draft lifecycle & anomaly rules
│   ├── sanitize/                 # Untrusted text wrappers
│   ├── relay/                    # Bridge connection broker
│   └── audit/                    # Append-only hash chain
├── bridge/                       # Windows Bridge Service
│   ├── templates/                # XML allow-list templates
│   ├── tally_adapter/            # Tally XML builder & decimal parser
│   └── installer/                # Service scripts
├── web/                          # Human approval portal & Admin console
├── tests/                        # Reconciliation, unit & red-team suites
├── db/migrations/                # PostgreSQL schema migrations
└── docs/                         # Specifications & implementation guides
```

---

## Security & Governance

- **Zero Direct Writes**: TallyGuard MCP never issues voucher creations directly from AI prompts.
- **Strict Anomaly Detection**: High-value amounts, new parties, and backdated transactions trigger mandatory flags requiring elevated approver rights.
- **Reporting Vulnerabilities**: See [SECURITY.md](SECURITY.md) for vulnerability disclosure procedures.

---

## Documentation

- [Master Development Plan & Progress Tracker](docs/DEVELOPMENT_PLAN.md)
- [Master Test Plan (All Scenarios & Layers)](docs/TEST_PLAN.md)
- [Operational Runbooks](docs/RUNBOOKS.md)
- [Full Specification](docs/SPECIFICATION.md)
- [Implementation Guide](docs/IMPLEMENTATION.md)
- [Contributing Guidelines](CONTRIBUTING.md)

---

## License

This project is licensed under the [MIT License](LICENSE).
