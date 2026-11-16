# TallyGuard MCP Implementation Guide

This document specifies the technical design, directory architecture, module contracts, and phased development guide for implementing **TallyGuard MCP**.

---

## 1. Architecture Overview

TallyGuard MCP decouples AI client interactions from direct accounting software mutations:

```
+-----------------------------------+
| AI Assistant (Claude / MCP Client)|
+-----------------+-----------------+
                  | MCP (stdio or Streamable HTTP)
                  v
+-----------------------------------+
|      TallyGuard MCP Server        |
|  - AuthZ & Scope Enforcement      |
|  - Input Validation (Pydantic)    |
|  - Prompt Injection Sanitizer     |
|  - Anomaly Rules Engine           |
|  - Append-Only Hash-Chained Audit |
+-----------------+-----------------+
                  | Internal Relay (Broker / Outbound TLS)
                  v
+-----------------------------------+
|   On-Premises Windows Bridge      |
|  - Template Allow-List Engine     |
|  - Local XML/HTTP Adapter         |
|  - Exact Decimal Math Engine      |
+-----------------+-----------------+
                  | Localhost XML/HTTP (Default Port 9000)
                  v
+-----------------------------------+
|    Tally Prime / Tally ERP 9      |
+-----------------------------------+
```

---

## 2. Directory Layout & Module Responsibilities

```
tallyguard-mcp/
├── server/
│   ├── mcp/                      # MCP Server implementation
│   │   ├── tools/                # Read and Draft tool handlers
│   │   ├── resources/            # Readable tally:// URIs
│   │   ├── prompts/              # System prompt templates
│   │   └── schemas/              # Pydantic v2 validation models
│   ├── auth/                     # OAuth 2.1, Scopes & Allow-lists
│   ├── drafts/                   # Draft lifecycle, Anomaly rules & Hashing
│   ├── sanitize/                 # Untrusted text wrappers & cleaners
│   ├── relay/                    # Bridge connection broker
│   └── audit/                    # Hash-chained append-only logging
├── bridge/
│   ├── templates/                # Approved Tally XML request templates
│   ├── tally_adapter/            # Tally XML parser & decimal converter
│   └── installer/                # Windows service setup scripts
├── web/
│   ├── approval/                 # Human out-of-band approval web app
│   └── admin/                    # Admin portal
├── tests/
│   ├── fixtures/                 # Reference company data & ground-truth exports
│   ├── simulated_tally/          # Mock Tally HTTP/XML test server
│   ├── agent_eval/               # 100-task agent tool evaluation suite
│   └── redteam/                  # Prompt injection & privilege attack suite
├── db/
│   └── migrations/               # PostgreSQL 16 schema migrations
└── docs/                         # Specification & architecture documentation
```

---

## 3. Core Engine Implementations

### 3.1 Untrusted Text Sanitization (`server/sanitize/`)
All text sourced from Tally (narrations, ledger names, remarks, item descriptions) must be treated as untrusted data:
1. Strip non-printable and ASCII control characters (`\x00-\x1F\x7F`).
2. Neutralize instruction-like markup (e.g., `<system>`, `[INST]`, `### Instruction`).
3. Wrap in a structured container:
```json
{
  "untrusted_text": {
    "content": "Received payment for invoice #1024",
    "sanitized": true
  }
}
```

### 3.2 Exact Decimal Currency Math (`bridge/tally_adapter/decimal_math.py`)
Floating point representations (`float`) are strictly forbidden in monetary calculations:
- All values are parsed as Python `Decimal` with 2 decimal places (`Decimal("0.01")`).
- Internal serialization uses exact string decimals (e.g. `"15400.50"`).
- Running balance calculations match Tally's rounding rules (`ROUND_HALF_UP`).

### 3.3 Draft Lifecycle & Cryptographic Binding (`server/drafts/`)
1. **Creation**: When an AI client calls `draft_receipt_voucher`, a draft record is created in PostgreSQL with status `pending_approval`.
2. **Payload Hashing**:
   $$\text{payload\_hash} = \text{SHA256}(\text{canonical\_json}(\text{payload}))$$
3. **Approval Validation**:
   When a human approves the draft at `/approve/{draft_id}`, the approval record computes:
   $$\text{approvals.payload\_hash} \stackrel{?}{=} \text{drafts.payload\_hash}$$
   If any discrepancy exists, the approval is invalidated.
4. **Posting**: The bridge receives the approved payload, generates an `idempotency_key`, submits it to Tally, and verifies the generated voucher number.

### 3.4 Append-Only Audit Log Hash Chain (`server/audit/`)
Each audit entry links cryptographically to the prior entry:
$$\text{entry\_hash} = \text{HMAC-SHA256}(K, \text{prev\_hash} \parallel \text{correlation\_id} \parallel \text{tool} \parallel \text{args\_hash} \parallel \text{status})$$

---

## 4. Development & Implementation Phases

### Phase 1: Foundation, Simulated Tally & Read Tools
- Build `tests/simulated_tally/server.py` to emulate Tally's local XML/HTTP service.
- Construct XML request/response templates for company info, ledgers, party ledgers, and ageing reports.
- Implement read tools in `server/mcp/tools/` using decimal-exact parsing.
- Run reconciliation tests to verify exact match against fixture exports.

### Phase 2: Security Controls, Auth & Audit Log
- Implement `server/sanitize/` untrusted text wrapping.
- Implement OAuth 2.1 token verification and scope checking.
- Construct the hash-chained audit logging service.
- Implement ledger/group allow-list filters.

### Phase 3: Draft Engine & Approval Service
- Implement draft tools (`draft_receipt_voucher`, `draft_sales_voucher`).
- Build the anomaly detection rules engine (thresholds, new parties, backdated dates, duplicates).
- Implement the web-based approval interface and REST endpoints (`GET /approve/{draft_id}`, `POST /approve/{draft_id}`).
- Implement idempotent voucher posting via the bridge.

### Phase 4: Hardening & Evaluation
- Execute the 100-task Agent Evaluation Suite to verify $\ge 95\%$ tool selection accuracy.
- Run the Red-Team Suite testing poisoned narrations and multi-step prompt injection attacks.
- Verify zero unapproved writes and zero unauthorized data access.

### Phase 5: Packaging & Release
- Package the Windows bridge agent with auto-reconnect and health checks.
- Document deployment, backup, and runbook operations.
