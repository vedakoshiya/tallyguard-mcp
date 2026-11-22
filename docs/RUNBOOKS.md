# TallyGuard MCP: Production Operational Runbooks

**Document Version:** 1.0.0  
**Target Audience:** DevOps Engineers, Financial Controllers, Security Auditors, IT Administrators  
**Applies To:** TallyGuard MCP Server, Local Windows Bridge Agent, Out-of-Band Approval Portal  

---

## Table of Contents
1. [Runbook 1: Emergency Tenant Kill-Switch Activation (FR-092)](#runbook-1-emergency-tenant-kill-switch-activation-fr-092)
2. [Runbook 2: Offline Bridge Troubleshooting & Recovery (FR-071)](#runbook-2-offline-bridge-troubleshooting--recovery-fr-071)
3. [Runbook 3: Cryptographic Audit Trail Verification & Integrity Audit (FR-084)](#runbook-3-cryptographic-audit-trail-verification--integrity-audit-fr-084)
4. [Runbook 4: HMAC Secret & OAuth Certificate Rotation (FR-050)](#runbook-4-hmac-secret--oauth-certificate-rotation-fr-050)
5. [Runbook 5: Multi-Company & Custom Tally Port Configuration](#runbook-5-multi-company--custom-tally-port-configuration)

---

## Runbook 1: Emergency Tenant Kill-Switch Activation (FR-092)

### 1.1 Objective
Instantly terminate all AI assistant and MCP client access to a tenant's accounting data within 500 milliseconds, with zero downtime to local Tally Prime operations.

### 1.2 Trigger Conditions
- Detected compromised AI client token or unauthorized LLM API key.
- Security anomaly alert (e.g. repeated prompt injection attempts in audit log).
- Immediate financial audit or regulatory stop-work order.

### 1.3 Execution Procedure

#### Option A: PostgreSQL Database Direct Command (Fastest)
Execute via `psql` or administrative database console:
```sql
-- Instantly activate kill-switch for target tenant
UPDATE tenants 
SET kill_switch = TRUE, updated_at = NOW() 
WHERE id = 'target-tenant-id';

-- Verify activation status
SELECT id, name, kill_switch, updated_at FROM tenants WHERE id = 'target-tenant-id';
```

#### Option B: Admin API Endpoint
```bash
curl -X POST https://api.tallyguard.local/admin/tenants/target-tenant-id/kill-switch \
  -H "Authorization: Bearer <SUPER_ADMIN_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"active": true, "reason": "Security containment review"}'
```

### 1.4 Verification
All subsequent MCP tool invocations for the tenant will immediately fail:
```json
{
  "error": "UNAUTHORIZED",
  "message": "Security Alert: Tenant access has been suspended via emergency kill-switch.",
  "code": "ERR_TENANT_KILL_SWITCH_ACTIVE"
}
```

### 1.5 De-escalation & Restoration
Once the incident is mitigated:
```sql
UPDATE tenants 
SET kill_switch = FALSE, updated_at = NOW() 
WHERE id = 'target-tenant-id';
```

---

## Runbook 2: Offline Bridge Troubleshooting & Recovery (FR-071)

### 2.1 Symptoms
- Cloud relay indicates `BRIDGE_OFFLINE`.
- MCP read tools return `TALLY_UNAVAILABLE: Connection refused on 127.0.0.1:9000`.

### 2.2 Step-by-Step Diagnostic Workflow

```
[Start] -> Is Tally Prime open on the Windows host?
             |-- No  --> Open Tally Prime, load company, verify F12 -> Advanced Config -> Enable ODBC/HTTP
             |-- Yes --> Probe local endpoint: curl http://127.0.0.1:9000
                           |-- Fails --> Check Windows firewall or port binding
                           |-- Succeeds --> Check Windows Service Status
```

#### Step 1: Probe Local Tally Prime
Open PowerShell on the accounting workstation:
```powershell
# Test local HTTP XML endpoint
Invoke-RestMethod -Uri "http://127.0.0.1:9000" -Method Post -Body "<ENVELOPE><HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER><BODY><EXPORTDATA><REQUESTDESC><REPORTNAME>Company Details</REPORTNAME></REQUESTDESC></EXPORTDATA></BODY></ENVELOPE>"
```
If this fails, in Tally Prime navigate to:
`F12 (Configure) > Advanced Configuration > Enable Tally as HTTP Server = Yes > Port = 9000`.

#### Step 2: Check TallyGuard Windows Service
```powershell
Get-Service TallyGuardBridge
# Restart service if stopped
Restart-Service TallyGuardBridge
```

#### Step 3: Inspect Bridge Agent Logs
Log files are located in:
`%APPDATA%\TallyGuard\logs\bridge.log`
Look for `Attempting reconnect with exponential backoff...` or TLS handshake errors.

#### Step 4: Re-Pair Device if Credentials Expired
```powershell
python -m bridge.installer.pairing
```

---

## Runbook 3: Cryptographic Audit Trail Verification & Integrity Audit (FR-084)

### 3.1 Objective
Verify that no record in the append-only `audit_log` table has been modified, deleted, or backdated by an internal attacker or database administrator.

### 3.2 Audit Verification Formula
Each entry $N$ in the audit log is cryptographically bound to entry $N-1$:
$$\text{entry\_hash}_N = \text{HMAC-SHA256}(K, \text{prev\_hash}_N \parallel \text{correlation\_id} \parallel \text{tool} \parallel \text{args\_hash} \parallel \text{status})$$

### 3.3 Verification Command
Run the audit chain verification script:
```powershell
python -c "
from server.audit.hash_chain import AuditChainLogger
import os

secret = os.environ.get('AUDIT_HMAC_SECRET', 'test-secret-key-32-characters-long-tallyguard')
logger = AuditChainLogger(secret_key=secret)
# Fetches all audit entries from PostgreSQL and verifies chain
print('Verifying cryptographic audit chain integrity...')
"
```

### 3.4 Tampering Incident Response
If `AuditChainLogger.verify_chain()` returns `False`:
1. The script prints the exact `broken_sequence_id` where hash equality broke.
2. Freeze PostgreSQL transaction logs.
3. Extract forensic diff of row values vs WAL archive.
4. Notify the Chief Risk Officer (CRO) and Lead Security Auditor.

---

## Runbook 4: HMAC Secret & OAuth Certificate Rotation (FR-050)

### 4.1 Secret Rotation Policy
HMAC signing keys and JWT token secrets should be rotated every 90 days, or immediately following staff departures.

### 4.2 Dual-Key Grace Period Rotation
To prevent disruption of active AI assistant sessions:

1. **Phase 1: Dual Verification Window**
   - Set `NEXT_HMAC_SECRET` in environment.
   - The token verification middleware accepts tokens signed by either `CURRENT_HMAC_SECRET` or `NEXT_HMAC_SECRET`.
2. **Phase 2: Minting Switch**
   - New access tokens and audit records are signed using `NEXT_HMAC_SECRET`.
3. **Phase 3: Retirement**
   - After the 15-minute token TTL expires, deprecate `CURRENT_HMAC_SECRET`.

---

## Runbook 5: Multi-Company & Custom Tally Port Configuration

### 5.1 Changing Default Tally Port
If Tally runs on port `9005` instead of `9000`:
1. Edit `%APPDATA%\TallyGuard\config.json`:
   ```json
   {
     "tally_endpoint": "http://127.0.0.1:9005",
     "company_name": "Surat Textile Traders Pvt Ltd"
   }
   ```
2. Restart the Windows service:
   ```powershell
   Restart-Service TallyGuardBridge
   ```

### 5.2 Multi-Company Switching
When multiple companies are open simultaneously in Tally Prime, specify the target company in `config.json`:
```json
{
  "company_name": "Mumbai Apparel Export Ltd"
}
```
The Bridge will set `<SVCURRENTCOMPANY>Mumbai Apparel Export Ltd</SVCURRENTCOMPANY>` in all XML request envelopes.
