# API Contracts: Jira Source Connector

**Feature**: 003-jira-connector
**Date**: 2026-03-05
**Base Path**: `/api/v1`

---

## 1. Create Jira Source

### Request

```http
POST /api/v1/sources
Content-Type: application/json
X-Tenant-ID: <tenant-schema>
Authorization: Bearer <jwt-token>
```

```json
{
  "name": "My Jira Instance",
  "source_type": "jira",
  "host": "https://company.atlassian.net",
  "port": 443,
  "database": "",
  "username": "user@example.com",
  "password": "ATATT3xFfGF0T...",
  "description": "Company Jira Cloud"
}
```

### Response 201 (Success)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "My Jira Instance",
  "source_type": "jira",
  "host": "https://company.atlassian.net",
  "username": "user@example.com",
  "connection_status": "connected",
  "last_validated_at": "2026-03-05T14:30:00Z",
  "description": "Company Jira Cloud",
  "created_at": "2026-03-05T14:30:00Z",
  "updated_at": "2026-03-05T14:30:00Z"
}
```

### Response 400 (Validation Error)

```json
{
  "detail": "Base URL must be a valid HTTPS URL",
  "error_code": "VALIDATION_ERROR"
}
```

### Response 401 (Auth Error - Jira API)

```json
{
  "detail": "Authentication failed. Check your email and API token.",
  "error_code": "AUTH_ERROR",
  "error_type": "auth",
  "suggestion": "Generate a new API token in Jira Settings > Security > API tokens"
}
```

---

## 2. Update Jira Source

### Request

```http
PATCH /api/v1/sources/{source_id}
Content-Type: application/json
X-Tenant-ID: <tenant-schema>
Authorization: Bearer <jwt-token>
```

```json
{
  "name": "Renamed Jira",
  "host": "https://new-company.atlassian.net",
  "password": "NEW_API_TOKEN"
}
```

### Response 200 (Success)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Renamed Jira",
  "source_type": "jira",
  "host": "https://new-company.atlassian.net",
  "username": "user@example.com",
  "connection_status": "connected",
  "last_validated_at": "2026-03-05T14:35:00Z",
  "updated_at": "2026-03-05T14:35:00Z"
}
```

---

## 3. Test Jira Connection

### Request

```http
POST /api/v1/sources/{source_id}/test
X-Tenant-ID: <tenant-schema>
Authorization: Bearer <jwt-token>
```

### Response 200 (Success)

```json
{
  "success": true,
  "message": "Connection successful",
  "user_info": {
    "display_name": "John Doe",
    "account_id": "5b10a2844c20165700ede21g"
  }
}
```

### Response 400 (Failure)

```json
{
  "success": false,
  "message": "Authentication failed",
  "error_type": "auth",
  "suggestion": "Verify your API token has not expired"
}
```

---

## 4. Get Available Projects

### Request

```http
GET /api/v1/sources/{source_id}/jira/projects
X-Tenant-ID: <tenant-schema>
Authorization: Bearer <jwt-token>
```

### Response 200

```json
{
  "projects": [
    {
      "key": "PROJ1",
      "name": "Project One",
      "id": "10000",
      "lead": {
        "display_name": "John Doe",
        "account_id": "5b10a2844c20165700ede21g"
      }
    },
    {
      "key": "PROJ2",
      "name": "Project Two",
      "id": "10001",
      "lead": {
        "display_name": "Jane Smith",
        "account_id": "5b10a2844c20165700ede21h"
      }
    }
  ],
  "total_count": 2
}
```

### Response 400 (Not Jira Source)

```json
{
  "detail": "This endpoint is only available for Jira sources",
  "error_code": "INVALID_SOURCE_TYPE"
}
```

---

## 5. Get Available Streams

### Request

```http
GET /api/v1/sources/{source_id}/jira/streams
X-Tenant-ID: <tenant-schema>
Authorization: Bearer <jwt-token>
```

### Response 200

```json
{
  "streams": [
    {
      "name": "issues",
      "display_name": "Issues",
      "description": "Jira issues and tickets",
      "replication_method": "INCREMENTAL",
      "replication_keys": ["updated"],
      "primary_keys": ["id"],
      "parent_stream": null,
      "field_count": 45
    },
    {
      "name": "projects",
      "display_name": "Projects",
      "description": "Jira projects",
      "replication_method": "FULL_TABLE",
      "replication_keys": [],
      "primary_keys": ["id"],
      "parent_stream": null,
      "field_count": 20
    },
    {
      "name": "users",
      "display_name": "Users",
      "description": "Jira users",
      "replication_method": "FULL_TABLE",
      "replication_keys": [],
      "primary_keys": ["key"],
      "parent_stream": null,
      "field_count": 15
    },
    {
      "name": "worklogs",
      "display_name": "Worklogs",
      "description": "Time tracking entries",
      "replication_method": "INCREMENTAL",
      "replication_keys": ["updated"],
      "primary_keys": ["id"],
      "parent_stream": "issues",
      "field_count": 12
    },
    {
      "name": "changelogs",
      "display_name": "Change Logs",
      "description": "Issue history and changes",
      "replication_method": "INCREMENTAL",
      "replication_keys": ["created"],
      "primary_keys": ["id"],
      "parent_stream": "issues",
      "field_count": 10
    },
    {
      "name": "issue_comments",
      "display_name": "Issue Comments",
      "description": "Comments on issues",
      "replication_method": "INCREMENTAL",
      "replication_keys": ["created"],
      "primary_keys": ["id"],
      "parent_stream": "issues",
      "field_count": 8
    }
  ],
  "total_count": 6
}
```

---

## 6. Get Stream Schema

### Request

```http
GET /api/v1/sources/{source_id}/jira/streams/{stream_name}/schema
X-Tenant-ID: <tenant-schema>
Authorization: Bearer <jwt-token>
```

### Response 200

```json
{
  "stream_name": "issues",
  "schema": {
    "type": "object",
    "properties": {
      "id": {"type": "string"},
      "key": {"type": "string"},
      "summary": {"type": "string"},
      "description": {"type": ["string", "null"]},
      "status": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "name": {"type": "string"},
          "category": {"type": "string"}
        }
      },
      "priority": {
        "type": ["object", "null"],
        "properties": {
          "id": {"type": "string"},
          "name": {"type": "string"}
        }
      },
      "assignee": {
        "type": ["object", "null"],
        "properties": {
          "account_id": {"type": "string"},
          "display_name": {"type": "string"},
          "email": {"type": ["string", "null"]}
        }
      },
      "reporter": {
        "type": "object",
        "properties": {
          "account_id": {"type": "string"},
          "display_name": {"type": "string"}
        }
      },
      "created": {"type": "string", "format": "date-time"},
      "updated": {"type": "string", "format": "date-time"},
      "project": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "key": {"type": "string"},
          "name": {"type": "string"}
        }
      }
    }
  },
  "field_count": 45,
  "replication_key": "updated"
}
```

---

## 7. Update Extraction Config

### Request

```http
PATCH /api/v1/sources/{source_id}/extraction-config
Content-Type: application/json
X-Tenant-ID: <tenant-schema>
Authorization: Bearer <jwt-token>
```

```json
{
  "streams": ["issues", "projects", "users"],
  "start_date": "2026-01-01T00:00:00Z",
  "batch_size": 50,
  "project_keys": ["PROJ1", "PROJ2"],
  "incremental_enabled": true,
  "replication_key": "updated"
}
```

### Response 200

```json
{
  "source_id": "550e8400-e29b-41d4-a716-446655440000",
  "extraction_config": {
    "streams": ["issues", "projects", "users"],
    "start_date": "2026-01-01T00:00:00Z",
    "batch_size": 50,
    "project_keys": ["PROJ1", "PROJ2"],
    "incremental_enabled": true,
    "replication_key": "updated"
  },
  "updated_at": "2026-03-05T14:40:00Z"
}
```

### Response 400 (Dependency Error)

```json
{
  "detail": "Stream 'worklogs' requires 'issues' to be selected",
  "error_code": "STREAM_DEPENDENCY",
  "missing_dependencies": ["issues"]
}
```

---

## 8. Preview Jira Data

### Request

```http
POST /api/v1/sources/{source_id}/jira/preview
Content-Type: application/json
X-Tenant-ID: <tenant-schema>
Authorization: Bearer <jwt-token>
```

```json
{
  "streams": ["issues"],
  "project_keys": ["PROJ1"],
  "start_date": "2026-02-01T00:00:00Z",
  "limit": 100
}
```

### Response 200 (Success)

```json
{
  "preview_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "completed",
  "started_at": "2026-03-05T14:45:00Z",
  "completed_at": "2026-03-05T14:45:15Z",
  "streams": {
    "issues": {
      "record_count": 42,
      "schema": {
        "type": "object",
        "properties": {...}
      },
      "sample_records": [
        {
          "id": "10001",
          "key": "PROJ1-123",
          "summary": "Sample issue title",
          "status": {"name": "In Progress"},
          "priority": {"name": "Medium"},
          "assignee": {"display_name": "John Doe"},
          "created": "2026-02-15T10:00:00Z",
          "updated": "2026-03-01T14:30:00Z"
        }
      ]
    }
  }
}
```

### Response 202 (Preview In Progress)

```json
{
  "preview_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "running",
  "started_at": "2026-03-05T14:45:00Z",
  "message": "Preview is running. Poll for results."
}
```

### Response 400 (Preview Failed)

```json
{
  "preview_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "failed",
  "error": {
    "type": "network",
    "message": "Connection timed out after 30 seconds",
    "suggestion": "Check if Jira URL is accessible from this network"
  }
}
```

---

## Error Types

| Type | HTTP Code | User Message Template |
|------|-----------|----------------------|
| `auth` | 401, 403 | "Authentication failed. Check your email and API token." |
| `network` | 502, 504 | "Network error. Check if Jira URL is accessible." |
| `config` | 400 | "Configuration error: {detail}" |
| `runtime` | 429, 500, 503 | "Temporary Jira error. Please try again later." |
| `rate_limit` | 429 | "Jira API rate limit exceeded. Please reduce batch size or wait." |

---

## Authentication & Authorization

All endpoints require:
1. **JWT Token**: Valid OIDC token from Keycloak
2. **Tenant Header**: `X-Tenant-ID` for schema routing
3. **Role Check**: User must have `User` or `Admin` role

### Role-Based Access

| Endpoint | User | Admin |
|----------|------|-------|
| Create Source | ✅ | ✅ |
| Update Source | ✅ (own) | ✅ (all) |
| Delete Source | ✅ (own) | ✅ (all) |
| Test Connection | ✅ | ✅ |
| Preview | ✅ | ✅ |
| View Credentials | ❌ | Partial (masked) |
