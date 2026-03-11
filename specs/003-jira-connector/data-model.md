# Data Model: Jira Source Connector

**Feature**: 003-jira-connector
**Date**: 2026-03-05

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      sources (existing)                      │
├─────────────────────────────────────────────────────────────┤
│ id: UUID (PK)                                                │
│ name: String                                                 │
│ source_type: String = 'jira'  ◄── NEW VALUE                 │
│ host: String                  ◄── stores base_url           │
│ port: Integer                 ◄── 443 for Jira              │
│ database: String              ◄── null for Jira             │
│ username: String              ◄── stores email              │
│ connection_status: String                                    │
│ last_validated_at: DateTime                                  │
│ validation_error: Text                                       │
│ extraction_config: JSON       ◄── NEW FIELD                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ 1:1
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              source_credentials (existing)                   │
├─────────────────────────────────────────────────────────────┤
│ id: UUID (PK)                                                │
│ source_id: UUID (FK → sources)                               │
│ password_encrypted: Binary    ◄── stores API token          │
│ rotated_at: DateTime                                         │
│ rotation_due_at: DateTime                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ 1:N
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       flows (existing)                       │
├─────────────────────────────────────────────────────────────┤
│ id: UUID (PK)                                                │
│ source_id: UUID (FK → sources)                               │
│ name: String                                                 │
│ status: String                                               │
│ ...                                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Schema Changes

### 1. sources table — Add extraction_config

**Migration**: `alembic revision -m "add_extraction_config_to_sources"`

```python
# backend/migrations/versions/XXX_add_extraction_config_to_sources.py

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

def upgrade():
    op.add_column(
        'sources',
        sa.Column('extraction_config', JSONB, nullable=True)
    )

def downgrade():
    op.drop_column('sources', 'extraction_config')
```

### 2. Source Model Extension

```python
# backend/src/models/source.py

from sqlalchemy.dialects.postgresql import JSONB

class Source(Base, TimestampMixin):
    # ... existing fields ...

    # New field for Jira connector configuration
    extraction_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None
    )
```

---

## New Data Structures

### JiraExtractionConfig (JSON Schema)

Stored in `sources.extraction_config` when `source_type = 'jira'`:

```json
{
  "streams": ["issues", "projects", "users"],
  "start_date": "2026-01-01T00:00:00Z",
  "batch_size": 100,
  "project_keys": ["PROJ1", "PROJ2"],
  "incremental_enabled": true,
  "replication_key": "updated"
}
```

**Field Definitions**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `streams` | string[] | Yes | `["issues"]` | List of tap-jira streams to sync |
| `start_date` | string | No | `null` | ISO datetime for incremental start |
| `batch_size` | integer | No | `100` | Number of records per API request |
| `project_keys` | string[] | No | `[]` | Specific project keys to sync (empty = all) |
| `incremental_enabled` | boolean | No | `false` | Enable incremental replication |
| `replication_key` | string | No | `"updated"` | Field to use for incremental bookmark |

---

### JiraStreamMetadata (Runtime)

Not stored in DB — computed from tap-jira catalog:

```python
@dataclass
class JiraStreamMetadata:
    name: str
    replication_method: str  # "INCREMENTAL" | "FULL_TABLE"
    primary_key: list[str]
    replication_key: str | None
    fields: list[dict]
    parent_stream: str | None  # For dependency tracking
```

**Static Definition** (hardcoded in service):

```python
JIRA_STREAMS = {
    "issues": JiraStreamMetadata(
        name="issues",
        replication_method="INCREMENTAL",
        primary_key=["id"],
        replication_key="updated",
        parent_stream=None,
        fields=[
            {"name": "id", "type": "string"},
            {"name": "key", "type": "string"},
            {"name": "summary", "type": "string"},
            {"name": "status", "type": "object"},
            {"name": "priority", "type": "object"},
            {"name": "assignee", "type": "object"},
            {"name": "created", "type": "datetime"},
            {"name": "updated", "type": "datetime"},
            # ... more fields
        ]
    ),
    "projects": JiraStreamMetadata(
        name="projects",
        replication_method="FULL_TABLE",
        primary_key=["id"],
        replication_key=None,
        parent_stream=None,
        fields=[...]
    ),
    "users": JiraStreamMetadata(
        name="users",
        replication_method="FULL_TABLE",
        primary_key=["key"],
        replication_key=None,
        parent_stream=None,
        fields=[...]
    ),
    "worklogs": JiraStreamMetadata(
        name="worklogs",
        replication_method="INCREMENTAL",
        primary_key=["id"],
        replication_key="updated",
        parent_stream="issues",  # Requires issues to be synced
        fields=[...]
    ),
    # ... other streams
}
```

---

## Validation Rules

### Source Creation/Update

| Field | Rule | Error Message |
|-------|------|---------------|
| `source_type` | Must be `'jira'` | "Invalid source type" |
| `host` | Must be valid HTTPS URL | "Base URL must be a valid HTTPS URL" |
| `username` | Must be valid email | "Email must be a valid email address" |
| `password` (API token) | Min 1 char on create | "API token is required" |
| `extraction_config.streams` | Must be non-empty array | "At least one stream must be selected" |
| `extraction_config.start_date` | Must be ISO datetime if provided | "Start date must be in ISO format" |
| `extraction_config.batch_size` | 1-1000 range | "Batch size must be between 1 and 1000" |

### Stream Selection

| Rule | Behavior |
|------|----------|
| Selecting `worklogs` | Auto-select `issues` (parent dependency) |
| Selecting `issue_comments` | Auto-select `issues` (parent dependency) |
| Selecting `changelogs` | Auto-select `issues` (parent dependency) |
| Selecting `issue_transitions` | Auto-select `issues` (parent dependency) |

---

## State Management

### Meltano State File

Location: `meltano/.meltano/run/tap-jira/target-postgres/state.json`

```json
{
  "bookmarks": {
    "issues": {
      "updated": "2026-03-05T14:30:00.000Z"
    },
    "worklogs": {
      "updated": "2026-03-05T14:30:00.000Z"
    }
  }
}
```

### State Tracking in runs table

Existing `runs` table already tracks:
- `state_file_path`: Path to Meltano state file
- `records_processed`: Count of records synced
- `started_at`, `completed_at`: Timing metrics

No changes needed to runs table.

---

## Data Flow

```
┌──────────────┐     ┌───────────────┐     ┌─────────────────┐
│   Jira API   │────►│   tap-jira    │────►│ target-postgres │
│ (Cloud/DC)   │     │  (Meltano)    │     │  (Business DB)  │
└──────────────┘     └───────────────┘     └─────────────────┘
                            │
                            │ reads config from
                            ▼
                     ┌─────────────────┐
                     │  meltano.yml    │
                     │  (generated)    │
                     └─────────────────┘
                            ▲
                            │ generated by
                     ┌─────────────────┐
                     │  FastAPI        │
                     │  source_service │
                     └─────────────────┘
                            ▲
                            │ reads from
                     ┌─────────────────┐
                     │  sources        │
                     │  (System DB)    │
                     └─────────────────┘
```

---

## Index Recommendations

No new indexes required. Existing indexes on `sources`:
- `idx_sources_type` — already indexes `source_type`
- `idx_sources_status` — already indexes `connection_status`

For Business DB (target tables), Meltano creates appropriate indexes automatically.
