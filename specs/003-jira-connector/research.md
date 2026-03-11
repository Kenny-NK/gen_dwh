# Research: Jira Source Connector

**Feature**: 003-jira-connector
**Date**: 2026-03-05
**Status**: Complete

## 1. Meltano tap-jira Installation & Configuration

### Decision
Use Meltano's built-in tap-jira extractor (singer-io variant).

### Installation Commands
```bash
# Via Meltano CLI
meltano add extractor tap-jira

# Via pip (alternative)
pip install tap-jira
```

### Required Configuration Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | Yes | Jira Cloud URL (e.g., `https://company.atlassian.net`) |
| `username` | string | Yes | Email address for Jira account |
| `password` | string | Yes | API token (NOT password) |
| `start_date` | datetime | No | Start date for incremental replication |
| `user_agent` | string | No | Custom user agent string |

### Configuration Example (meltano.yml)
```yaml
plugins:
  extractors:
    - name: tap-jira
      variant: singer-io
      pip_url: tap-jira
      config:
        start_date: "2024-01-01T00:00:00Z"
        username: "user@example.com"
        password: "${JIRA_API_TOKEN}"
        base_url: "https://company.atlassian.net"
        user_agent: "tap-jira user@example.com"
      select:
        - issues.*
        - projects.*
        - users.*
```

### Rationale
- Meltano-native installation ensures compatibility with existing pipeline infrastructure
- singer-io variant is the most maintained and documented
- Environment variable substitution (`${JIRA_API_TOKEN}`) keeps secrets out of config files

---

## 2. Available Streams

### Decision
Support all 12 tap-jira streams with UI-based selection.

### Stream Inventory
| Stream | Replication Method | Primary Key | Supports Incremental |
|--------|-------------------|-------------|---------------------|
| `issues` | INCREMENTAL | id | Yes (via `updated` field) |
| `projects` | FULL_TABLE | id | No |
| `users` | FULL_TABLE | key | No |
| `worklogs` | INCREMENTAL | id | Yes (via `updated` field) |
| `changelogs` | INCREMENTAL | id | Yes |
| `issue_comments` | INCREMENTAL | id | Yes |
| `issue_transitions` | INCREMENTAL | id, issueId | Yes |
| `versions` | FULL_TABLE | id | No |
| `components` | FULL_TABLE | id | No |
| `project_types` | FULL_TABLE | key | No |
| `project_categories` | FULL_TABLE | id | No |
| `resolutions` | FULL_TABLE | id | No |

### Stream Dependencies
Some streams require parent streams to be synced first:
- `changelogs` → requires `issues`
- `issue_comments` → requires `issues`
- `issue_transitions` → requires `issues`
- `worklogs` → requires `issues`

### Rationale
- All 12 streams should be selectable in UI for flexibility
- Dependency handling: auto-select parent streams when child is selected
- Incremental streams are prioritized for large datasets

---

## 3. Replication Keys & Incremental Loading

### Decision
Use `updated` field as replication key for incremental streams.

### Incremental Configuration
```yaml
# In tap-jira config
start_date: "2026-01-01T00:00:00Z"  # Initial sync start date

# State is automatically managed by Meltano
# State file stores: {"issues": {"updated": "2026-03-05T10:00:00Z"}}
```

### Supported Replication Keys
| Stream | Replication Key | Notes |
|--------|----------------|-------|
| `issues` | `updated` | Last update timestamp |
| `worklogs` | `updated` | Last update timestamp |
| `changelogs` | `created` | Creation timestamp |
| `issue_comments` | `created` | Creation timestamp |
| `issue_transitions` | `created` | Creation timestamp |

### Rationale
- `updated` field is most useful for CDC-style incremental loads
- `start_date` provides initial baseline for first sync
- Meltano state management handles bookmark persistence automatically

---

## 4. JQL Filtering

### Finding
**tap-jira does NOT support custom JQL filtering in configuration.**

### Workaround Options

**Option A: Use stream selection (Selected)**
- Use Meltano's `select` filter to choose specific streams
- Configure at flow level with project-based filtering in UI
- Apply post-extraction filtering in target database

**Option B: Custom tap fork (Rejected)**
- Would require maintaining custom tap-jira fork
- Increases maintenance burden significantly

**Option C: Pre-filter via API calls (Rejected)**
- Would require direct API integration bypassing Meltano
- Violates Constitution Principle II (Meltano-First)

### Decision
- UI will NOT expose JQL input field (not supported by tap)
- Instead, UI will allow:
  1. Project selection (sync all issues from selected projects)
  2. Date range filtering (via `start_date` config)
  3. Stream selection (which entity types to sync)
- Filtering logic applied post-load in target database via SQL views

### Rationale
- Maintains Meltano-native approach
- Avoids custom fork maintenance
- Users can still filter data via SQL after loading

---

## 5. Authentication Methods

### Decision
Support Basic Auth (email + API token) as primary method. OAuth2 deferred to future iteration.

### Basic Auth (Selected for MVP)
```
username: user@example.com
password: <API_TOKEN>
base_url: https://company.atlassian.net
```

### OAuth2 (Deferred)
```
cloud_id: <Jira Cloud ID>
access_token: <OAuth access token>
refresh_token: <OAuth refresh token>
oauth_client_id: <OAuth app client ID>
oauth_client_secret: <OAuth app client secret>
```

### Rationale
- Basic Auth with API token is simpler to configure in UI
- Most Jira Cloud users can generate API tokens easily
- OAuth2 requires app registration in Atlassian Developer Console
- OAuth2 can be added in Phase 2 if needed

---

## 6. Known Limitations & Mitigations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Worklog 1000-record bookmark | Large worklog syncs may miss records | Document limitation; suggest full resync for large datasets |
| No built-in rate limiting | May hit Jira API rate limits | Configure smaller batch sizes; add retry logic |
| No custom JQL support | Cannot filter issues at source | Use post-load SQL filtering |
| Parent-child stream dependencies | Must sync parent streams first | Auto-select parent streams in UI |
| API deprecation concerns | Future Jira API changes may break tap | Monitor tap-jira releases; test regularly |

---

## 7. Implementation Approach

### Configuration Mapping

| Source Field | DB Storage | UI Field | Validation |
|--------------|------------|----------|------------|
| `base_url` | `sources.host` | Base URL | HTTPS URL format |
| `username` | `sources.username` | Email | Valid email format |
| `password` | `source_credentials.password_encrypted` | API Token | Required, masked |
| `start_date` | JSON config | Start Date | ISO datetime |
| Stream selection | JSON config | Streams | Multi-select |

### Meltano Config Generation
```python
def generate_jira_config(source: Source, extraction_config: dict) -> dict:
    return {
        "base_url": source.host,
        "username": source.username,
        "password": "${JIRA_API_TOKEN}",  # Injected at runtime
        "start_date": extraction_config.get("start_date", "2026-01-01T00:00:00Z"),
        "user_agent": f"tap-jira {source.username}",
        "select": extraction_config.get("streams", ["issues.*", "projects.*"]),
    }
```

---

## Summary

| Aspect | Decision |
|--------|----------|
| **Installation** | Meltano CLI (`meltano add extractor tap-jira`) |
| **Streams** | All 12 streams with dependency handling |
| **Replication** | INCREMENTAL via `updated` field for issues/worklogs |
| **Filtering** | No JQL; use project selection + post-load SQL |
| **Auth** | Basic Auth (email + API token) |
| **Config Storage** | Reuse `sources` table + JSON `extraction_config` |
