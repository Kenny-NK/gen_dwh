# Quickstart: Jira Source Connector

**Feature**: 003-jira-connector
**Date**: 2026-03-05

## Prerequisites

1. **Jira Cloud Account** with API token access
2. **API Token** generated from [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
3. **Admin access** to Jira projects you want to sync (for project listing)
4. **Running GenDWH instance** with backend and frontend services

---

## Step 1: Generate Jira API Token

1. Navigate to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **"Create API token"**
3. Label it (e.g., "GenDWH Integration")
4. Copy the token (shown only once!)

```
Example token: ATATT3xFfGF0T1h3Vkc1...
```

---

## Step 2: Create Jira Source

### Via UI

1. Navigate to **Sources** page
2. Click **"Create Source"**
3. Select type **"Jira"**
4. Fill in:
   - **Name**: `My Jira Instance`
   - **Base URL**: `https://your-company.atlassian.net`
   - **Email**: `your-email@company.com`
   - **API Token**: (paste from Step 1)
5. Click **"Save & Validate"**

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "X-Tenant-ID: my_tenant" \
  -d '{
    "name": "My Jira Instance",
    "source_type": "jira",
    "host": "https://your-company.atlassian.net",
    "port": 443,
    "database": "",
    "username": "your-email@company.com",
    "password": "ATATT3xFfGF0T1h3Vkc1..."
  }'
```

**Expected Response**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "My Jira Instance",
  "source_type": "jira",
  "connection_status": "valid"
}
```

---

## Step 3: Configure Extraction

### Get Available Projects

```bash
curl http://localhost:8000/api/v1/sources/{source_id}/jira/projects \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "X-Tenant-ID: my_tenant"
```

### Get Available Streams

```bash
curl http://localhost:8000/api/v1/sources/{source_id}/jira/streams \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "X-Tenant-ID: my_tenant"
```

### Set Extraction Config

```bash
curl -X PATCH http://localhost:8000/api/v1/sources/{source_id}/extraction-config \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "X-Tenant-ID: my_tenant" \
  -d '{
    "streams": ["issues", "projects", "users"],
    "start_date": "2026-01-01T00:00:00Z",
    "batch_size": 100,
    "project_keys": ["PROJ1", "PROJ2"],
    "incremental_enabled": true
  }'
```

---

## Step 4: Preview Data

```bash
curl -X POST http://localhost:8000/api/v1/sources/{source_id}/jira/preview \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "X-Tenant-ID: my_tenant" \
  -d '{
    "streams": ["issues"],
    "project_keys": ["PROJ1"],
    "batch_size": 100
  }'
```

**Expected Response**:
```json
{
  "success": true,
  "streams": ["issues"],
  "records": {"issues": []},
  "schema": {"issues": {}},
  "record_count": 0
}
```

---

## Step 5: Create Flow

### Via UI

1. After successful preview, click **"Create Flow"**
2. Configure target:
   - **Target Schema**: `jira_data`
   - **Write Mode**: `upsert`
3. Configure schedule (optional)
4. Click **"Create"**

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/flows \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "X-Tenant-ID: my_tenant" \
  -d '{
    "name": "Jira Issues Sync",
    "source_id": "550e8400-e29b-41d4-a716-446655440000",
    "target_schema": "jira_data",
    "write_mode": "upsert"
  }'
```

```bash
curl -X POST http://localhost:8000/api/v1/flows/{flow_id}/tables \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "X-Tenant-ID: my_tenant" \
  -d '{
    "source_schema": "jira",
    "source_table": "issues",
    "target_table": "issues",
    "replication_method": "INCREMENTAL",
    "replication_key": "updated"
  }'
```

---

## Step 6: Run Flow

### Manual Trigger

```bash
curl -X POST http://localhost:8000/api/v1/flows/{flow_id}/run \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "X-Tenant-ID: my_tenant"
```

### Check Status

```bash
curl http://localhost:8000/api/v1/runs/{run_id} \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "X-Tenant-ID: my_tenant"
```

---

## Verify Data in Target

```sql
-- Connect to business database
\c gendwh_business

-- Check issues table
SELECT key, summary, status, updated
FROM jira_data.issues
ORDER BY updated DESC
LIMIT 10;
```

---

## Troubleshooting

### Connection Failed

| Error | Solution |
|-------|----------|
| "Authentication failed" | Verify email and API token are correct |
| "Network error" | Check if `base_url` is accessible; verify firewall rules |
| "SSL certificate error" | Ensure `base_url` uses HTTPS with valid certificate |

### Preview Returns Empty

| Cause | Solution |
|-------|----------|
| No projects selected | Select at least one project |
| `start_date` too recent | Set earlier `start_date` |
| No matching issues | Verify project has issues in selected date range |

### Rate Limit Errors

| Error | Solution |
|-------|----------|
| "429 Too Many Requests" | Reduce `batch_size` to 50 or lower |
| Consistent timeouts | Jira API may be slow; retry with smaller batches |

---

## Development Setup

### Install tap-jira in Meltano

```bash
cd meltano
meltano add extractor tap-jira
```

### Configure for Local Development

```yaml
# meltano/meltano.yml
plugins:
  extractors:
    - name: tap-jira
      variant: singer-io
      pip_url: tap-jira
      config:
        start_date: "2026-01-01T00:00:00Z"
        username: "${JIRA_EMAIL}"
        password: "${JIRA_API_TOKEN}"
        base_url: "${JIRA_BASE_URL}"
```

### Test Extraction

```bash
cd meltano
meltano invoke tap-jira --discover
```

---

## Environment Variables

```bash
# Required for Meltano execution
JIRA_BASE_URL=https://company.atlassian.net
JIRA_EMAIL=user@example.com
JIRA_API_TOKEN=ATATT3xFfGF0T1h3Vkc1...
```
