# Data Model: Data Pipeline MVP

**Feature**: 001-data-pipeline-mvp
**Date**: 2026-03-01

---

## Database Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     System Database                          │
├─────────────────────────────────────────────────────────────┤
│  public schema (shared)                                      │
│  ├── tenants                                                 │
│  └── users                                                   │
├─────────────────────────────────────────────────────────────┤
│  tenant_{id} schema (per-tenant, isolated)                   │
│  ├── sources                                                 │
│  ├── source_credentials                                      │
│  ├── flows                                                   │
│  ├── flow_tables                                             │
│  ├── runs                                                    │
│  ├── schedules                                               │
│  ├── notifications                                           │
│  └── audit_events                                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Business Database                         │
├─────────────────────────────────────────────────────────────┤
│  tenant_{id} schema (per-tenant)                             │
│  └── {extracted_tables}                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Entities

### 1. Tenant (public schema)

```sql
CREATE TABLE public.tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subdomain VARCHAR(63) UNIQUE NOT NULL,  -- e.g., "tenant1" from tenant1.app.com
    schema_name VARCHAR(63) UNIQUE NOT NULL,  -- e.g., "tenant_acme"
    keycloak_realm VARCHAR(100),  -- Keycloak realm for this tenant
    name VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tenants_subdomain ON public.tenants(subdomain);
```

### 2. User (public schema)

```sql
CREATE TABLE public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    keycloak_id VARCHAR(255) NOT NULL,  -- Keycloak user ID (sub claim)
    email VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, keycloak_id)
);

CREATE INDEX idx_users_tenant ON public.users(tenant_id);
CREATE INDEX idx_users_keycloak ON public.users(keycloak_id);
```

### 3. Source Connection (tenant schema)

```sql
CREATE TABLE {tenant_schema}.sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Connection parameters
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL DEFAULT 5432,
    database VARCHAR(255) NOT NULL,
    username VARCHAR(255) NOT NULL,

    -- Validation status
    connection_status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (connection_status IN ('pending', 'valid', 'invalid')),
    last_validated_at TIMESTAMPTZ,
    validation_error TEXT,

    -- Metadata
    created_by UUID REFERENCES public.users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ  -- Soft delete
);

CREATE INDEX idx_sources_status ON {tenant_schema}.sources(connection_status);
```

### 4. Source Credentials (tenant schema)

```sql
CREATE TABLE {tenant_schema}.source_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES {tenant_schema}.sources(id) ON DELETE CASCADE,
    password_encrypted BYTEA NOT NULL,  -- pgp_sym_encrypt result

    -- Rotation tracking
    rotated_at TIMESTAMPTZ,
    rotation_due_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(source_id)
);
```

### 5. Data Flow (tenant schema)

```sql
CREATE TABLE {tenant_schema}.flows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Source reference
    source_id UUID NOT NULL REFERENCES {tenant_schema}.sources(id),

    -- Target configuration
    target_schema VARCHAR(63) NOT NULL,  -- Schema in Business DB
    target_table_prefix VARCHAR(63),  -- Optional prefix for all tables

    -- Flow state
    status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'paused', 'running', 'success', 'failed')),
    status_reason TEXT,  -- Reason for current status (e.g., error message)

    -- Write configuration
    write_mode VARCHAR(20) NOT NULL DEFAULT 'append'
        CHECK (write_mode IN ('append', 'upsert', 'replace')),
    upsert_key VARCHAR(255),  -- Column name(s) for upsert

    -- Metadata
    created_by UUID REFERENCES public.users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ  -- Soft delete
);

CREATE INDEX idx_flows_source ON {tenant_schema}.flows(source_id);
CREATE INDEX idx_flows_status ON {tenant_schema}.flows(status);
```

### 6. Flow Table (tenant schema)

```sql
-- Individual table configuration within a flow
CREATE TABLE {tenant_schema}.flow_tables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flow_id UUID NOT NULL REFERENCES {tenant_schema}.flows(id) ON DELETE CASCADE,

    -- Source table selection
    source_schema VARCHAR(63) NOT NULL,
    source_table VARCHAR(63) NOT NULL,

    -- Target table name (defaults to source_table)
    target_table VARCHAR(63) NOT NULL,

    -- Replication configuration
    replication_method VARCHAR(20) NOT NULL DEFAULT 'FULL_TABLE'
        CHECK (replication_method IN ('FULL_TABLE', 'INCREMENTAL')),
    replication_key VARCHAR(255),  -- Cursor field for incremental

    -- Column selection (null = all columns)
    selected_columns JSONB,  -- ["col1", "col2", ...]

    -- Sensitivity markers
    sensitive_columns JSONB,  -- {"col1": "pii_email", "col2": "sensitive"}

    -- State tracking
    last_cursor_value TEXT,  -- Last seen replication_key value

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(flow_id, source_schema, source_table)
);

CREATE INDEX idx_flow_tables_flow ON {tenant_schema}.flow_tables(flow_id);
```

### 7. Run Record (tenant schema)

```sql
CREATE TABLE {tenant_schema}.runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flow_id UUID NOT NULL REFERENCES {tenant_schema}.flows(id),

    -- Run identification
    run_number INTEGER NOT NULL,  -- Sequential per flow
    triggered_by VARCHAR(20) NOT NULL
        CHECK (triggered_by IN ('manual', 'scheduled', 'retry')),

    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'success', 'failed', 'cancelled')),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Metrics
    tables_processed INTEGER DEFAULT 0,
    records_processed BIGINT DEFAULT 0,
    records_failed BIGINT DEFAULT 0,

    -- Error information
    error_message TEXT,
    error_details JSONB,  -- Structured error info
    retry_count INTEGER DEFAULT 0,

    -- Meltano state
    meltano_state_file VARCHAR(500),  -- Path to state file

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_runs_flow ON {tenant_schema}.runs(flow_id);
CREATE INDEX idx_runs_status ON {tenant_schema}.runs(status);
CREATE INDEX idx_runs_created ON {tenant_schema}.runs(created_at);
```

### 8. Schedule (tenant schema)

```sql
CREATE TABLE {tenant_schema}.schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flow_id UUID NOT NULL REFERENCES {tenant_schema}.flows(id) ON DELETE CASCADE,

    -- Schedule type
    schedule_type VARCHAR(20) NOT NULL
        CHECK (schedule_type IN ('cron', 'interval', 'manual')),

    -- Cron expression (if schedule_type = 'cron')
    cron_expression VARCHAR(100),  -- e.g., "0 */6 * * *"

    -- Interval (if schedule_type = 'interval')
    interval_minutes INTEGER,

    -- Timezone
    timezone VARCHAR(50) NOT NULL DEFAULT 'Europe/Moscow',

    -- Execution constraints
    max_retries INTEGER DEFAULT 5,
    timeout_minutes INTEGER DEFAULT 120,

    -- State
    is_active BOOLEAN DEFAULT true,
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,

    created_by UUID REFERENCES public.users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_schedules_flow ON {tenant_schema}.schedules(flow_id);
CREATE INDEX idx_schedules_next_run ON {tenant_schema}.schedules(next_run_at) WHERE is_active = true;
```

### 9. Notification (tenant schema)

```sql
CREATE TABLE {tenant_schema}.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Target
    user_id UUID REFERENCES public.users(id),
    is_broadcast BOOLEAN DEFAULT false,  -- If true, shown to all tenant users

    -- Content
    type VARCHAR(20) NOT NULL
        CHECK (type IN ('success', 'error', 'warning', 'info')),
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,

    -- Reference
    related_entity_type VARCHAR(50),  -- 'flow', 'run', 'source'
    related_entity_id UUID,

    -- State
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_notifications_user ON {tenant_schema}.notifications(user_id) WHERE is_read = false;
CREATE INDEX idx_notifications_created ON {tenant_schema}.notifications(created_at);
```

### 10. Audit Event (tenant schema)

```sql
CREATE TABLE {tenant_schema}.audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Actor
    user_id UUID REFERENCES public.users(id),
    user_email VARCHAR(255),

    -- Action
    action VARCHAR(50) NOT NULL,  -- e.g., 'source.create', 'flow.run', 'flow.pause'
    entity_type VARCHAR(50) NOT NULL,  -- 'source', 'flow', 'run', 'schedule'
    entity_id UUID,

    -- Details
    changes JSONB,  -- Before/after values for updates

    -- Context
    ip_address INET,
    user_agent TEXT,

    created_at TIMESTAMPTZ DEFAULT now()
);

-- Retention: 100 days (via pg_cron or application cleanup)
CREATE INDEX idx_audit_events_user ON {tenant_schema}.audit_events(user_id);
CREATE INDEX idx_audit_events_entity ON {tenant_schema}.audit_events(entity_type, entity_id);
CREATE INDEX idx_audit_events_created ON {tenant_schema}.audit_events(created_at);
```

---

## State Transitions

### Flow Status

```
                    ┌─────────┐
                    │  draft  │
                    └────┬────┘
                         │ save & activate
                         ▼
┌──────────────────────►┤ paused ├──────────────────────┐
│                      └────┬────┘                      │
│                           │ start                     │
│                           ▼                           │
│                      ┌─────────┐                      │
│      ┌──────────────►│ running │◄─────────────┐      │
│      │               └────┬────┘              │      │
│      │                    │                   │      │
│      │    ┌───────────────┼───────────────┐   │      │
│      │    │               │               │   │      │
│      │    ▼               ▼               │   │      │
│      │ ┌────────┐    ┌─────────┐          │   │      │
│      │ │ failed │    │ success │          │   │      │
│      │ └────┬───┘    └────┬────┘          │   │      │
│      │      │              │               │   │      │
│      │      │ retry        │ pause         │   │      │
│      │      └──────────────┴───────────────┘   │      │
│      │                                         │      │
│      └─────────────────────────────────────────┘      │
│                                                        │
└────────────────────────────────────────────────────────┘
              pause (from any non-running state)
```

**Allowed transitions**:
| From | To | Trigger |
|------|-----|---------|
| draft | paused | User activates flow |
| paused | running | Manual start or scheduled trigger |
| running | success | All tables processed without errors |
| running | failed | Error after 5 retries |
| failed | running | Manual retry |
| success | paused | User pauses flow |
| failed | paused | User pauses flow |
| paused | paused | Schedule update (no-op) |

### Run Status

```
┌─────────┐
│ pending │
└────┬────┘
     │ worker picks up
     ▼
┌─────────┐     success    ┌─────────┐
│ running │ ──────────────►│ success │
└────┬────┘                └─────────┘
     │
     │ error (after retries)
     ▼
┌─────────┐
│ failed  │
└─────────┘
     ▲
     │ user cancellation
┌────────────┐
│ cancelled  │
└────────────┘
```

---

## Relationships

```
public.tenants
    │
    ├── 1:N ──► public.users
    │
    └── schema per tenant ──► {tenant_schema}.sources
                                   │
                                   ├── 1:1 ──► {tenant_schema}.source_credentials
                                   │
                                   └── 1:N ──► {tenant_schema}.flows
                                                   │
                                                   ├── 1:N ──► {tenant_schema}.flow_tables
                                                   │
                                                   ├── 1:N ──► {tenant_schema}.runs
                                                   │
                                                   └── 1:1 ──► {tenant_schema}.schedules

{tenant_schema}.runs
    │
    └── 1:N ──► {tenant_schema}.notifications (via related_entity_id)

public.users
    │
    └── 1:N ──► {tenant_schema}.audit_events
```

---

## Indexes Summary

| Table | Index | Purpose |
|-------|-------|---------|
| tenants | subdomain | Tenant lookup by subdomain |
| users | tenant_id | Filter users by tenant |
| users | keycloak_id | Auth lookup |
| sources | connection_status | Filter by validation status |
| flows | source_id | Get flows for source |
| flows | status | Filter by flow status |
| flow_tables | flow_id | Get tables for flow |
| runs | flow_id | Get run history |
| runs | created_at | Time-based queries |
| schedules | next_run_at | Scheduler queries |
| notifications | user_id, is_read | Unread notification count |
| audit_events | created_at | Retention cleanup |
