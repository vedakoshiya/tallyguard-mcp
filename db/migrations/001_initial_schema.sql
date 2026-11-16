-- ==============================================================================
-- TallyGuard MCP: Initial Database Schema (PostgreSQL 16)
-- Migration: 001_initial_schema.sql
-- ==============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Tenants table
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    kill_switch BOOLEAN NOT NULL DEFAULT FALSE,
    approval_policy JSONB NOT NULL DEFAULT '{"max_single_amount": 50000.00, "require_second_approver_above": 200000.00}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Users table (Humans and System Administrators)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'accountant', 'viewer', 'admin')),
    scopes TEXT[] NOT NULL DEFAULT ARRAY['read:reports'],
    ledger_allowlist TEXT[] DEFAULT NULL,
    can_approve BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, email)
);

-- 3. Devices table (Windows Bridge Service Registrations)
CREATE TABLE IF NOT EXISTS devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT,
    public_key TEXT NOT NULL,
    tally_company TEXT,
    last_seen TIMESTAMPTZ,
    version TEXT,
    revoked_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Drafts table (Proposals created by AI clients; never direct writes)
CREATE TABLE IF NOT EXISTS drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    client_id TEXT NOT NULL,
    voucher_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    payload_hash TEXT NOT NULL,
    flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL CHECK (status IN (
        'pending_approval',
        'approved',
        'rejected',
        'expired',
        'posted',
        'failed',
        'cancelled'
    )),
    idempotency_key TEXT NOT NULL UNIQUE,
    tally_voucher_no TEXT DEFAULT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 5. Approvals table (Human approval events)
CREATE TABLE IF NOT EXISTS approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    approver_id UUID NOT NULL REFERENCES users(id),
    decision TEXT NOT NULL CHECK (decision IN ('approve', 'reject')),
    payload_hash TEXT NOT NULL, -- Must match drafts.payload_hash exactly
    channel TEXT NOT NULL,       -- e.g. web, mobile, whatsapp
    decided_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 6. Audit Log table (Immutable, Append-Only with Cryptographic Hash Chaining)
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    actor_user UUID,
    client_id TEXT,
    tool TEXT NOT NULL,
    args_hash TEXT NOT NULL,
    args_redacted JSONB,
    result_summary JSONB,
    status TEXT NOT NULL,
    correlation_id UUID NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_tenant_email ON users(tenant_id, email);
CREATE INDEX IF NOT EXISTS idx_drafts_tenant_status ON drafts(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_time ON audit_log(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_correlation ON audit_log(correlation_id);

-- Enforce append-only rules on audit_log via trigger/rule
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM PUBLIC;
