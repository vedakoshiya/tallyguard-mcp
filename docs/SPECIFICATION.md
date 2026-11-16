# TallyGuard MCP Specification

**A Governed Model Context Protocol Server for Safe AI Access to Tally Accounting Data**

| Field | Value |
|---|---|
| Document Type | PRD + SRS + Technical Design |
| Version | 0.1 (Draft) |
| Status | Approved for Implementation |
| Owner | Vedansi |
| Working Name | TallyGuard MCP |

---

## 1. Overview

### 1.1 Purpose
TallyGuard MCP exposes a business's Tally accounting data to AI assistants through the Model Context Protocol (MCP), with enterprise-grade security, approval, and audit controls designed for financial systems.
- **Read operations** are safe by default and side-effect free.
- **Write operations** only ever create **drafts** that a designated human must approve before anything is posted to the books.

### 1.2 Problem Statement
Tally Prime / ERP 9 is the primary system of record for Indian businesses, but it is desktop software communicating over local XML/HTTP with no native AI governance. Direct, unmediated connectors grant LLMs broad access to financial ledgers and posting capabilities with zero approval gates, no role-based scoping, and no defense against prompt injection hidden inside customer narrations, remarks, or imported ledger titles.

### 1.3 Product Vision
An owner or accountant asks an AI assistant: *"Which five parties owe me the most and haven't paid in 45 days?"* and receives an answer reconciled to Tally to the exact paisa. The assistant can prepare a receipt or sales voucher draft, and a human approves it out-of-band via an authenticated portal. Every action is logged in an append-only, hash-chained audit log.

### 1.4 Goals
- **G1**: Read tools return figures that reconcile exactly (to the paisa) with Tally's own reports.
- **G2**: Zero unapproved writes — no voucher is created, altered, or deleted without an explicit human approval event.
- **G3**: Zero successful prompt-injection actions in the red-team suite.
- **G4**: Tool-selection accuracy of 95% or higher on the agent test suite across at least two LLM clients.
- **G5**: Setup time under 20 minutes for a Windows machine running Tally, with zero inbound firewall ports opened.
- **G6**: p95 read-tool latency under 3 seconds for company data up to 100,000 vouchers.

### 1.5 Non-Goals (v1)
- Deleting or altering posted vouchers (v1 is strictly create-draft only).
- Payroll, TDS return filing, or GST return filing.
- Replacing Tally's UI or operating as an independent accounting engine.
- Direct support for non-Tally systems in v1 (though designed with an adapter interface for future systems).
- Multi-company consolidation across different customers in a single session.

### 1.6 Glossary
- **MCP**: Model Context Protocol, open standard for exposing tools, resources, and prompts to AI models.
- **Voucher**: A transaction record in Tally (Receipt, Payment, Sales, Purchase, Journal).
- **Ledger**: An individual account in the Chart of Accounts.
- **Bridge Agent**: A local Windows service interfacing with Tally locally and dialing out to the relay.
- **Draft**: A proposed voucher stored externally, pending human approval.
- **Elicitation**: MCP protocol feature for requesting missing user parameters or confirmation.

---

## 2. Personas & User Stories

### Personas
- **P1: Business Owner**: Needs quick summaries on money owed, inventory, and sales without opening Tally.
- **P2: Accountant / Munshi**: Primary approver of drafts. Demands exact figures, debit/credit reconciliations, and audit trails.
- **P3: IT / Integrator**: Deploys bridge, provisions tenant scopes, manages tokens.
- **P4: AI Client Developer**: Connects AI models (Claude Desktop, custom agents); requires strict schemas and error semantics.
- **P5: Security Reviewer**: Inspects threat models, hash-chained logs, and red-team test suites.

### User Stories
- **US-01**: Receivables ageing categorized in buckets (0-30, 31-60, 61-90, 90+ days) matching Tally's report.
- **US-02**: Party ledger extraction across date ranges with opening, running, and closing balances.
- **US-03**: Paginated voucher search by type, party, amount range, date range, or narration with stable ordering.
- **US-04**: Draft receipt generation returning a human-readable diff without modifying Tally books.
- **US-05**: Out-of-band draft approval/rejection with authenticated approver identity; on approval, the bridge posts the payload and returns the Tally voucher number.
- **US-06**: Immutable audit trail logging actor, client, tool, arguments hash, result summary, and timestamp.
- **US-07**: Scope restrictions and ledger/group allow-lists with deterministic authorization failures.
- **US-08**: Defense against malicious data in narrations or remarks preventing prompt injection.
- **US-09**: Guided bridge pairing using a one-time code over an outbound-only connection.

---

## 3. Functional Requirements

### 3.1 MCP Surface

#### Read Tools (Side-Effect Free)
- **FR-001**: `get_company_info`: Company name, financial year, books-from date, base currency.
- **FR-002**: `list_ledgers`: Filters by group, name prefix; cursor-paginated.
- **FR-003**: `get_party_ledger`: (party, from, to) returning transaction entries, opening, closing balances.
- **FR-004**: `get_receivables_ageing`: (as_on, buckets, min_amount, top_n).
- **FR-005**: `get_payables_ageing`: Same parameters as receivables for outstanding liabilities.
- **FR-006**: `search_vouchers`: Filter by voucher type, party, amount range, date range, narration text; paginated.
- **FR-007**: `get_stock_summary`: Item/group, as_on date.
- **FR-008**: `get_gst_summary`: Outward/inward tax totals for a period.
- **FR-009**: `get_trial_balance`, `get_profit_and_loss`, `get_balance_sheet`: Financial reports by period.

#### Write Tools (Draft-Only)
- **FR-020**: `draft_receipt_voucher`: (party, amount, date, bank/cash ledger, reference, narration).
- **FR-021**: `draft_sales_voucher`: (party, items[], rates, taxes, date, narration).
- **FR-022**: `draft_payment_voucher`, `draft_journal_voucher`.
- **FR-023**: `get_draft_status`: (draft_id) and `cancel_draft`: (draft_id, creator only).
- **FR-024**: Every draft tool returns `draft_id`, normalized payload, validation report, and approval URL; never writes to Tally.

#### Resources & Prompts
- **FR-030**: `tally://company/{id}/chart-of-accounts`, `.../parties`, `.../items` with caching and ETags.
- **FR-031**: `tally://company/{id}/reports/{name}?period=` for pre-computed reports.
- **FR-035**: Parameterized prompt templates: `weekly_collections_review`, `month_end_checklist`, `gst_prep_summary`.

#### Protocol Features
- **FR-040**: Streamable HTTP transport and local stdio mode.
- **FR-041**: Strict JSON Schema with explicit tool annotations (`readOnlyHint`, `openWorldHint: false`).
- **FR-042**: Opaque cursor pagination.
- **FR-043**: Parameter elicitation for missing inputs or draft review confirmation.
- **FR-044**: Stable error codes: `UNAUTHORIZED`, `SCOPE_DENIED`, `TALLY_UNAVAILABLE`, `VALIDATION_FAILED`, `RATE_LIMITED`, `APPROVAL_REQUIRED`.

### 3.2 Authentication & Security Controls
- **FR-050**: OAuth 2.1 with PKCE; short-lived access tokens and refresh tokens.
- **FR-051**: Scopes: `read:reports`, `read:ledgers`, `read:vouchers`, `read:stock`, `draft:vouchers`, `admin:users`.
- **FR-053**: Human-only approval scope (`approve:vouchers`), never grantable to AI tokens.
- **FR-080**: All free text from Tally books wrapped in delimited `untrusted_text` blocks and sanitized of control codes and prompt injection sequences.
- **FR-084**: Hash-chained, append-only audit log with cryptographic hash verification.
- **FR-092**: Tenant kill-switch to instantly terminate all AI access.

### 3.3 Bridge Agent & Approval Engine
- **FR-070**: Windows service auto-discovering local Tally XML/HTTP endpoint.
- **FR-071**: Outbound-only TLS/WebSocket connection to cloud relay.
- **FR-072**: Strict template allow-list; arbitrary XML execution from cloud is rejected.
- **FR-062**: Anomaly engine flagging high values, new parties, backdated entries, and duplicates.
- **FR-065**: Cryptographic hash matching (`approvals.payload_hash == drafts.payload_hash`) prior to posting.
