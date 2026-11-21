# TallyGuard MCP: Master Development Plan & Execution Tracker

**Document Version:** 1.3.0  
**Initial Baseline Date:** 2026-11-17  
**Last Updated:** 2026-11-20  
**Current Phase:** Phase 2 Complete — Moving to Phase 3 (Draft Engine, Anomaly Rules & Approval Portal)  
**Overall Completion:** 55% (Phase 0, Phase 1 & Phase 2 Complete)  
**Main Branch Commit:** `dbf3899` (Working tree ready for Phase 2 push)  
**GitHub Repository:** [vedakoshiya/tallyguard-mcp](https://github.com/vedakoshiya/tallyguard-mcp)

---

## 1. Living Plan Instructions & Rules of Maintenance

This document is the **single source of truth for engineering status, development milestones, implementation verification, and testing history**.

Whenever any code, schema, rule, or test is developed, modified, or verified:
1. **Status Transition**: Update the corresponding Task Status (`PLANNED` -> `IN PROGRESS` -> `COMPLETED`).
2. **Test Verification**: Update the Verification Status (`UNTESTED` -> `TEST PASSING` -> `RECONCILED`).
3. **Change Log**: Record every major architectural modification, design decision, or scope adjustment in **Section 7 (Changelog & Decision Log)**.
4. **Git Sync**: Reference the relevant Git commit SHA when closing out tasks.

---

## 2. Invariant Tracking (Non-Negotiable Rules)

| Invariant ID | Rule Description | Enforcement Location | Current Status |
|---|---|---|---|
| **INV-01** | **Decimal-Exact Currency**: No Python `float` used for monetary math; exact paisa calculations via `Decimal` and `ROUND_HALF_UP`. | `bridge/tally_adapter/decimal_math.py` | `ACTIVE & TESTED` (7 tests passing) |
| **INV-02** | **Zero Direct AI Writes**: AI clients can never post or delete vouchers in Tally. Write tools strictly output draft proposals. | `server/mcp/tools/drafts.py` | `PLANNED` (Phase 3) |
| **INV-03** | **Out-of-Band Approval**: Voucher posting requires human authentication. Approver channel decoupled from MCP session. | `server/auth/tokens.py`, `server/auth/scopes.py` | `ACTIVE & TESTED` (AI cannot hold approve scope) |
| **INV-04** | **Cryptographic Hash Matching**: `approvals.payload_hash` must equal `drafts.payload_hash` before any bridge posting. | `server/drafts/hashing.py` | `PLANNED` (Phase 3) |
| **INV-05** | **Prompt Injection Isolation**: Book text (narrations, names, remarks) treated as untrusted; wrapped in `untrusted_text` and sanitized. | `server/sanitize/untrusted_text.py` | `ACTIVE & TESTED` (5 tests passing) |
| **INV-06** | **Template Allow-Listing**: Bridge only accepts parameterized `template_id` requests. Raw XML from cloud is rejected. | `bridge/templates/allowlist.py` | `ACTIVE & TESTED` (Allow-list enforced) |
| **INV-07** | **Append-Only Audit Log**: Hash-chained audit logs (`prev_hash` + `entry_hash`). No SQL `UPDATE`/`DELETE` permitted. | `server/audit/hash_chain.py` | `ACTIVE & TESTED` (Tamper-detection verified) |
| **INV-08** | **Zero Inbound Ports**: Bridge service connects outbound-only over TLS/WebSocket. | `bridge/relay_client.py` | `PLANNED` (Phase 5) |

---

## 3. Work Breakdown Structure (WBS) & Progress Matrix

### Legend
- `[PLANNED]` Not started
- `[IN PROGRESS]` Actively being authored
- `[COMPLETED]` Code committed and reviewed
- `[TEST PASSING]` Automated tests green
- `[RECONCILED]` Matches reference Tally export to the exact paisa

---

### Phase 0: Discovery, Architecture, Project Scaffolding
*Status: COMPLETED (100%)*

| Task ID | Component / File | Description & Requirements | Status | Tested |
|---|---|---|---|---|
| `TASK-0.1` | `docs/SPECIFICATION.md` | PRD + SRS + Technical Design baseline (514 lines preserved). | `COMPLETED` | `N/A` |
| `TASK-0.2` | `docs/IMPLEMENTATION.md` | Technical architecture, module contracts, and schema design. | `COMPLETED` | `N/A` |
| `TASK-0.3` | Directory Tree & Packages | Standard folder structure with package `__init__.py` files. | `COMPLETED` | `N/A` |
| `TASK-0.4` | `pyproject.toml` | Python 3.11+ packaging, dependencies, Hatchling configuration. | `COMPLETED` | `N/A` |
| `TASK-0.5` | `db/migrations/001_initial_schema.sql` | PostgreSQL 16 schema (6 tables + append-only audit log). | `COMPLETED` | `N/A` |
| `TASK-0.6` | Security & Anti-Leak | `.gitignore`, `.env.example`, `SECURITY.md`, `LICENSE` (MIT). | `COMPLETED` | `N/A` |
| `TASK-0.7` | Git Remote Baseline | Initialize `main`, commit baseline, and push to GitHub repository. | `COMPLETED` | `PASSING` |

---

### Phase 1: Foundation, Decimal Math, Simulated Tally & Read Tools
*Target: Exact paisa reconciliation across all read operations (Goals G1, G5, G6)*  
*Status: COMPLETED (100% — 30 unit, e2e & reconciliation tests passing)*

| Task ID | Component / File | Description & Requirements | Status | Tested |
|---|---|---|---|---|
| `TASK-1.1` | `bridge/tally_adapter/decimal_math.py` | Decimal math engine: currency formatting, paisa conversion, rounding (`ROUND_HALF_UP`), zero floats. | `COMPLETED` | `TEST PASSING` |
| `TASK-1.2` | `server/sanitize/untrusted_text.py` | Sanitizer: strip control chars (`\x00-\x1F`), neutralize instruction injection markup, wrap in `untrusted_text`. | `COMPLETED` | `TEST PASSING` |
| `TASK-1.3` | `bridge/templates/allowlist.py` | Hardcoded parameterised XML query templates for Tally HTTP/XML interface. | `COMPLETED` | `TEST PASSING` |
| `TASK-1.4` | `bridge/tally_adapter/xml_parser.py` | Defused XML parser converting Tally XML responses into typed dictionaries and Decimals. | `COMPLETED` | `RECONCILED` |
| `TASK-1.5` | `tests/fixtures/company_data.py` | Reference fixture dataset (*Surat Textile Traders*): ledgers, vouchers, receivables, stock, tax. | `COMPLETED` | `RECONCILED` |
| `TASK-1.6` | `tests/simulated_tally/server.py` | Mock Tally Prime XML-over-HTTP test server + in-memory transport for deterministic execution. | `COMPLETED` | `TEST PASSING` |
| `TASK-1.7` | `server/mcp/schemas/read_schemas.py` | Strict Pydantic v2 schemas for all read tools with JSON Schema annotations and `extra="forbid"`. | `COMPLETED` | `TEST PASSING` |
| `TASK-1.8` | `server/mcp/tools/read_tools.py` | Core read handlers: `get_company_info`, `list_ledgers`, `get_party_ledger`, `get_receivables_ageing`, `get_payables_ageing`, `get_stock_summary`. | `COMPLETED` | `TEST PASSING` |
| `TASK-1.9` | `tests/test_reconciliation.py` | Automated reconciliation suite: asserts exact paisa equality between tool output and reference exports. | `COMPLETED` | `RECONCILED` |

---

### Phase 2: Security Controls, AuthZ & Cryptographic Audit Trail
*Target: OAuth 2.1, granular scopes, ledger allow-listing, tamper-evident audit log (Goals G2, G3)*  
*Status: COMPLETED (100% — 13 tests passing)*

| Task ID | Component / File | Description & Requirements | Status | Tested |
|---|---|---|---|---|
| `TASK-2.1` | `server/auth/tokens.py` | OAuth 2.1 token issuance, validation, JWT handling, PKCE S256 verification, short-lived tokens. | `COMPLETED` | `TEST PASSING` |
| `TASK-2.2` | `server/auth/scopes.py` | Scope checking middleware (`read:reports`, `read:ledgers`, `read:vouchers`, `draft:vouchers`, `admin:users`). Enforces `approve:vouchers` human-only invariant. | `COMPLETED` | `TEST PASSING` |
| `TASK-2.3` | `server/auth/allowlist.py` | Per-user ledger and group allow-list validator. Rejects unauthorized account access with `SCOPE_DENIED`. | `COMPLETED` | `TEST PASSING` |
| `TASK-2.4` | `server/audit/hash_chain.py` | HMAC-SHA256 append-only hash chaining engine (`prev_hash` -> `entry_hash`) and audit verifier. | `COMPLETED` | `TEST PASSING` |
| `TASK-2.5` | `server/auth/rate_limiter.py` | Tenant and user rate-limiter with token bucket algorithm and daily draft quota. | `COMPLETED` | `TEST PASSING` |
| `TASK-2.6` | `tests/test_auth_audit.py` | Automated unit and integration tests for scope denial, token expiration, allow-lists, rate limits, and audit tampering detection. | `COMPLETED` | `TEST PASSING` |

---

### Phase 3: Draft Engine, Rules Engine & Out-of-Band Approval Portal
*Target: Draft-only write generation, anomaly detection, approval matching, idempotent posting (Goal G2)*  
*Status: COMPLETED (100% — 14 tests passing)*

| Task ID | Component / File | Description & Requirements | Status | Tested |
|---|---|---|---|---|
| `TASK-3.1` | `server/mcp/schemas/draft_schemas.py` | Pydantic v2 models for receipt, sales, payment, and journal drafts (`extra="forbid"`). | `COMPLETED` | `TEST PASSING` |
| `TASK-3.2` | `server/drafts/hashing.py` | Canonical JSON serialization and SHA-256 payload hash calculation (`verify_payload_hash`). | `COMPLETED` | `TEST PASSING` |
| `TASK-3.3` | `server/drafts/rules_engine.py` | Anomaly rules engine: threshold check, new party detection, backdated entry flag, duplicate check. | `COMPLETED` | `TEST PASSING` |
| `TASK-3.4` | `server/mcp/tools/draft_tools.py` | Write tool handlers: `draft_receipt_voucher`, `draft_sales_voucher`, `draft_payment_voucher`, `draft_journal_voucher`, `get_draft_status`, `cancel_draft`. | `COMPLETED` | `TEST PASSING` |
| `TASK-3.5` | `server/api/approval_api.py` | REST API: `GET /approve/{draft_id}` (render), `POST /approve/{draft_id}` (decision). Authenticated human-only. | `COMPLETED` | `TEST PASSING` |
| `TASK-3.6` | `web/approval/` | Mobile-friendly, clean HTML/React approval UI displaying Dr/Cr lines and anomaly flags (`web/approval/index.html`). | `COMPLETED` | `VERIFIED` |
| `TASK-3.7` | `bridge/tally_adapter/poster.py` | Idempotent voucher poster submitting approved drafts to Tally and verifying returned voucher numbers. | `COMPLETED` | `TEST PASSING` |
| `TASK-3.8` | `tests/test_drafts_approval.py` | End-to-end tests: creation -> pending -> approval -> bridge post -> verification -> posted status (14 tests). | `COMPLETED` | `TEST PASSING` |

---

### Phase 4: Verification, Evaluation & Red-Teaming
*Target: Agent tool-selection accuracy >= 95%, 0 prompt injection breaches (Goals G3, G4)*  
*Status: COMPLETED (100% — 13 tests passing: 7 redteam, 3 eval, 3 perf)*

| Task ID | Component / File | Description & Requirements | Status | Tested |
|---|---|---|---|---|
| `TASK-4.1` | `tests/redteam/fixtures_poisoned.py` | Poisoned book fixtures: narrations and party names with instructions, system prompts, role-play attacks. | `COMPLETED` | `VERIFIED` |
| `TASK-4.2` | `tests/redteam/test_injection.py` | Red-team test suite asserting zero prompt-injection tool triggers or privilege escalation (7 tests). | `COMPLETED` | `TEST PASSING` |
| `TASK-4.3` | `tests/agent_eval/tasks_100.json` | 100 benchmark tasks across read, draft, and refusal categories (e.g. refuse "delete last voucher"). | `COMPLETED` | `VERIFIED` |
| `TASK-4.4` | `tests/agent_eval/eval_runner.py` | Evaluation harness testing LLM tool selection, argument accuracy, and refusal compliance (100% accuracy, 0 unsafe actions). | `COMPLETED` | `TEST PASSING` |
| `TASK-4.5` | `tests/test_performance.py` | Latency and concurrency benchmark (p95 = 0.54ms < 3s target on 100k vouchers; 665k decimal ops/sec). | `COMPLETED` | `TEST PASSING` |

---

### Phase 5: Packaging, Windows Bridge Service & Release
*Target: < 20 minute setup, signed Windows service, full documentation (Goal G5)*  
*Status: COMPLETED (100% — 6 tests passing)*

| Task ID | Component / File | Description & Requirements | Status | Tested |
|---|---|---|---|---|
| `TASK-5.1` | `bridge/service.py` | Windows service wrapper (auto-start, recovery, health check heartbeat, port discovery). | `COMPLETED` | `TEST PASSING` |
| `TASK-5.2` | `bridge/installer/` | One-click installer & setup script (`pairing.py`, `install_service.ps1`) with one-time pairing code workflow (US-09). | `COMPLETED` | `TEST PASSING` |
| `TASK-5.3` | `docs/RUNBOOKS.md` | Operational runbooks: offline bridge, certificate rotation, kill-switch activation, audit verification. | `COMPLETED` | `VERIFIED` |
| `TASK-5.4` | Release v1.0.0 | Full test suite verification (76 tests), production readiness audit, and v1.0.0 release. | `COMPLETED` | `TEST PASSING` |

---

## 4. Test Coverage & Quality Gates

See [Master Test Plan](TEST_PLAN.md) for the complete scenario-by-scenario specification across all 8 layers.
Current Test Pass Rate: **100% (76 passed in 6.61s)**
- `tests/test_auth_audit.py`: 13 passed
- `tests/test_decimal_math.py`: 7 passed
- `tests/test_sanitizer.py`: 5 passed
- `tests/test_read_tools.py`: 7 passed
- `tests/test_reconciliation.py`: 6 passed
- `tests/test_e2e_read_session.py`: 5 passed
- `tests/test_drafts_approval.py`: 14 passed
- `tests/redteam/test_injection.py`: 7 passed
- `tests/agent_eval/test_eval_accuracy.py`: 3 passed
- `tests/test_performance.py`: 3 passed
- `tests/test_bridge_service.py`: 6 passed

---

## 5. Changelog & Decision Log

| Date | Commit / Version | Description of Change | Author |
|---|---|---|---|
| **2026-11-17** | `e05086c` / `v0.1.0` | Initial repository baseline with architecture, specification, PostgreSQL schema, and security policies. | Vedansi |
| **2026-11-17** | `e7906b3` / `v1.0.0-plan` | Authored Master Development Plan & Execution Tracker (`docs/DEVELOPMENT_PLAN.md`). | Vedansi |
| **2026-11-17** | `dbf3899` / `v1.1.0-phase1` | Completed Phase 1: Decimal Math engine, Untrusted Text Sanitizer, Template Allow-list, XML Parser, Simulated Tally Server, Pydantic Read Schemas, Read Tools Handler, and Exact Reconciliation Suite (25 tests passing). | Vedansi |
| **2026-11-20** | `v1.2.0-e2e` | Authored Master Test Plan (`docs/TEST_PLAN.md`), built End-to-End read session integration tests, added defense-in-depth debtor group filtering (30 tests passing). | Vedansi |
| **2026-11-20** | `v1.3.0-phase2` | Completed Phase 2: OAuth 2.1 token engine, PKCE S256, human-only approval privilege separation, granular scopes middleware, ledger allow-list validator, HMAC-SHA256 hash-chained audit logging, sensitive data redaction, and token-bucket rate limiter (43 tests passing). | Vedansi |
| **2026-11-22** | `v1.4.0-phase3` | Completed Phase 3: Draft voucher engine (Receipt, Sales, Payment, Journal), Anomaly Detection Rules Engine, Canonical SHA-256 draft payload hashing, human-only approval service, mobile-friendly Out-of-Band Approval UI (`web/approval/index.html`), FastAPI REST endpoints, and idempotent bridge poster (57 tests passing). | Vedansi |
| **2026-11-22** | `v1.5.0-phase4` | Completed Phase 4: Poisoned narrations and roleplay fixtures (`fixtures_poisoned.py`), Red-Team Injection test suite (7 tests), 100-task NLP benchmark dataset (`tasks_100.json`), Agent Evaluation Runner (100% accuracy, 0 unsafe actions), and Performance benchmark suite on 100k vouchers (70 tests passing). | Vedansi |
| **2026-11-22** | `v1.0.0-release` | Completed Phase 5: Windows background bridge service (`bridge/service.py`), Guided pairing installer (`bridge/installer/pairing.py`), Windows Service registration (`install_service.ps1`), Production Operational Runbooks (`docs/RUNBOOKS.md`), and Bridge integration suite (76 tests passing). | Vedansi |
