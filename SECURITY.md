# Security Policy

## Reporting Security Issues

We take the security of TallyGuard MCP seriously. If you discover a security vulnerability or potential threat involving authentication, draft tampering, prompt injection bypass, or data exfiltration, please DO NOT open a public GitHub issue.

Please report vulnerabilities privately by emailing:
**koshiyaveda@gmail.com**

Please include:
1. Description of the vulnerability.
2. Steps or proof-of-concept scripts to reproduce the issue.
3. Affected components (server, bridge, relay, or web approval portal).
4. Any potential mitigations you have identified.

You will receive an acknowledgment within 48 hours, followed by regular status updates as the patch is prepared.

## Core Security Invariants

TallyGuard MCP is built on the following foundational security rules:

1. **Zero Direct AI Writes**: AI clients and agents never have write or delete permissions to Tally. Write operations only create drafts in an external database pending human approval.
2. **Separation of Privileges**: The `approve:vouchers` capability is strictly reserved for authenticated human approvers and is never issued to AI client tokens.
3. **Defense Against Prompt Injection**: All free-form text from Tally books (party names, narrations, line remarks) is treated as untrusted data, wrapped in delimited structures, and sanitized before returning to AI contexts.
4. **Outbound-Only Bridge**: The on-premises bridge agent initiates outbound TLS/WebSocket connections to the relay. No inbound ports or router pinholes are required.
5. **Template Allow-Listing**: The bridge only executes pre-approved XML query templates. Arbitrary XML strings from the cloud are rejected immediately.
6. **No Float Arithmetic**: All monetary quantities are represented and calculated using strict decimal math (to the exact paisa).
