# Research: Data Pipeline MVP

**Feature**: 001-data-pipeline-mvp
**Date**: 2026-03-01
**Purpose**: Resolve technical unknowns and document technology decisions

---

## 1. Meltano Integration

### Decision: Meltano 3.x with tap-postgres and target-postgres

**Rationale**: Meltano provides declarative ELT framework with built-in state management for incremental loads.

### tap-postgres Configuration

```yaml
# Meltano tap-postgres settings
host: ${SOURCE_HOST}
port: ${SOURCE_PORT}
user: ${SOURCE_USER}
password: ${SOURCE_PASSWORD}
database: ${SOURCE_DB}
default_replication_method: INCREMENTAL  # or FULL_TABLE
stream_maps: {}  # Per-table configuration
```

**Key capabilities**:
- `replication_method`: FULL_TABLE (full refresh) or INCREMENTAL
- `replication_key`: Cursor field for incremental (e.g., `updated_at`)
- `stream_maps`: Column selection, renaming, filtering

### target-postgres Configuration

```yaml
# Meltano target-postgres settings
host: ${TARGET_HOST}
port: ${TARGET_PORT}
user: ${TARGET_USER}
password: ${TARGET_PASSWORD}
database: ${TARGET_DB}
default_target_schema: ${TENANT_SCHEMA}  # e.g., tenant_acme
add_record_metadata: true  # Adds _sdc columns
```

**Write modes**:
- `append`: Insert all records
- `upsert`: Insert or update based on primary keys
- `overwrite` (replace): Drop and recreate table

### State Management

Meltano stores incremental state in `.meltano/run/` directory. For multi-tenant:
- State file per flow: `state_{tenant_id}_{flow_id}.json`
- Contains: `replication_key_value` for each stream

**Alternatives considered**:
- Custom PostgreSQL connector: Rejected - reinvents Meltano's state management
- Airbyte: Rejected - heavier deployment, less flexible configuration

---

## 2. Multi-Tenant Architecture

### Decision: Schema-per-tenant in System DB

**Rationale**: PostgreSQL-native, clear isolation, simple migrations.

### Tenant Resolution Flow

```
1. Request arrives with Host header: tenant1.app.com
2. API middleware extracts subdomain: "tenant1"
3. Lookup tenant_id from public.tenants table
4. Set search_path to tenant_schema (e.g., "tenant_acme")
5. All queries within request use tenant schema
```

### Schema Structure

```sql
-- Public schema (shared)
public.tenants (id, subdomain, schema_name, keycloak_realm, created_at)
public.users (id, tenant_id, keycloak_id, role, created_at)

-- Per-tenant schema (isolated)
tenant_acme.sources (...)
tenant_acme.flows (...)
tenant_acme.runs (...)
tenant_acme.audit_events (...)
```

### Business DB Schema

```sql
-- Per-tenant in Business DB
tenant_acme.extracted_table_1 (...)
tenant_acme.extracted_table_2 (...)
```

**Alternatives considered**:
- Database-per-tenant: Rejected - operational complexity, resource overhead
- Row-level tenant_id: Rejected - requires every query to filter, risk of leaks

---

## 3. Job Scheduling

### Decision: Celery + Redis with celery-beat

**Rationale**: Battle-tested, timezone-aware, integrates with FastAPI.

### Architecture

```
FastAPI → Celery Task Queue → Celery Worker → Meltano CLI
                ↑
         Redis (broker + result backend)
                ↑
         celery-beat (scheduler)
```

### Schedule Types

```python
# Cron schedule
schedule_type = "cron"
cron_expression = "0 */6 * * *"  # Every 6 hours
timezone = "Europe/Moscow"

# Interval schedule
schedule_type = "interval"
interval_minutes = 30

# Manual
schedule_type = "manual"  # No automatic scheduling
```

### Concurrency Control

```python
# Use PostgreSQL advisory lock to prevent parallel runs of same table
@celery_app.task(bind=True)
def run_flow(self, flow_id: str, tenant_id: str):
    lock_id = f"flow_{flow_id}_table_{source_table}".hash()

    with pg_advisory_lock(lock_id):
        # Execute Meltano run
        pass
```

**Alternatives considered**:
- APScheduler: Rejected - no distributed execution
- Prefect: Rejected - overkill for MVP, steeper learning curve
- Temporal: Rejected - operational complexity

---

## 4. Preview Implementation

### Decision: Meltano dry-run with streaming to temp schema

**Rationale**: Reuses Meltano infrastructure, consistent with actual extraction.

### Preview Flow

```
1. User clicks "Preview" in UI
2. API creates preview session (id, flow_config, row_limit=100)
3. Celery task runs Meltano with:
   - target_schema: preview_{session_id}
   - row_limit: 100 or 10000
4. Task completes, API queries preview_{session_id}.{table}
5. Apply masking for User role
6. Return paginated results
7. Cleanup preview schema after 1 hour TTL
```

### Performance

- Default 100 rows: Complete within 30 seconds
- Max 10000 rows: Complete within 5 minutes
- Pagination: 100 rows per page
- Sorting/filtering: Applied in PostgreSQL query

---

## 5. PII Detection and Masking

### Decision: Microsoft Presidio + custom patterns

**Rationale**: Industry-standard, extensible, supports Russian locale.

### Detection Patterns

```python
PII_PATTERNS = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "phone_ru": r"\+7[0-9]{10}|8[0-9]{10}",
    "credit_card": r"\b[0-9]{13,19}\b",
    "passport_ru": r"\b[0-9]{4}\s?[0-9]{6}\b",
}
```

### Masking Rules

| Type | Mask Pattern | Example |
|------|-------------|---------|
| email | `***@domain.com` | `j***@gmail.com` |
| phone | `+7***XXX**XX` | `+7***123**45` |
| credit_card | `****XXXX` | `****1234` |
| passport | `****XXXX` | `****5678` |

### Column Metadata

Meltano tap can include custom metadata:
```yaml
stream_maps:
  users:
    email:  # Auto-detected as PII
      _pii_type: email
    salary:  # Manually marked as sensitive
      _sensitive: true
```

---

## 6. Secret Management

### Decision: PostgreSQL pgcrypto with AES-256 for MVP

**Rationale**: Database-native, no external dependencies, acceptable for MVP.

### Encryption

```sql
-- Store encrypted credentials
INSERT INTO source_credentials (source_id, password_encrypted)
VALUES (
  :source_id,
  pgp_sym_encrypt(:password, :encryption_key)
);

-- Retrieve decrypted credentials
SELECT pgp_sym_decrypt(password_encrypted, :encryption_key) as password
FROM source_credentials
WHERE source_id = :source_id;
```

### Key Management

```bash
# Encryption key from environment
ENCRYPTION_KEY=${DB_ENCRYPTION_KEY}  # 32-byte hex string
```

**Phase 2 consideration**: Migrate to HashiCorp Vault for production.

---

## 7. Keycloak Integration

### Decision: OIDC with tenant-realm mapping

### Realm Structure

Option A (Recommended): Single realm with tenant claim
```
Keycloak Realm: gendwh
  - Client: gendwh-app
  - User attribute: tenant_id
  - Role mapping: realm roles (admin, user)
```

Option B: Multiple realms
```
Keycloak Realms: tenant-acme, tenant-foo
  - Each realm has its own users and roles
```

### Token Validation

```python
# FastAPI dependency
async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = jwt.decode(token, key, algorithms=["RS256"])
    tenant_id = payload.get("tenant_id")
    roles = payload.get("realm_access", {}).get("roles", [])
    return User(tenant_id=tenant_id, roles=roles)
```

### Role-Based Access

| Role | Permissions |
|------|-------------|
| Admin | Full access, see unmasked PII, view audit logs |
| User | Create/edit flows, masked preview, no audit access |

---

## 8. Error Handling and Retry

### Retry Policy

```python
# Celery task retry configuration
@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,  # 1 minute
    retry_backoff=True,      # Exponential backoff
    retry_backoff_max=600,   # Max 10 minutes
)
def run_flow(self, flow_id: str):
    try:
        execute_meltano_run(flow_id)
    except MeltanoError as e:
        if self.request.retries < 5:
            raise self.retry(exc=e)
        raise  # Mark as failed after 5 retries
```

### Error Categories

| Category | User Message | Retry |
|----------|-------------|-------|
| Connection refused | "Source database unavailable" | Yes |
| Auth failed | "Invalid credentials" | No |
| Schema change | "Table structure changed" | No |
| Timeout | "Operation timed out" | Yes |
| Unknown | "Unexpected error occurred" | No |

---

## 9. Observability

### Logging

```python
import structlog

logger = structlog.get_logger()
logger.info(
    "flow_started",
    flow_id=flow_id,
    tenant_id=tenant_id,
    source_table=source_table,
    run_id=run_id,
)
```

### Metrics

- `flow_runs_total{status="success|failed"}`
- `flow_duration_seconds{flow_id}`
- `flow_records_processed{flow_id}`
- `preview_requests_total`

### Health Checks

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": await check_db_connection(),
        "redis": await check_redis_connection(),
        "meltano": await check_meltano_available(),
    }
```
