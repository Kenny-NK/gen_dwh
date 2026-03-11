# Implementation Plan: Jira Source Connector

**Branch**: `003-jira-connector` | **Date**: 2026-03-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-jira-connector/spec.md`

## Summary

Добавление Jira-коннектора в систему GenDWH на базе Meltano tap-jira. Пользователь сможет подключить Jira через UI, настроить параметры извлечения (streams, projects, incremental), проверить данные через preview и создать поток для регулярной загрузки — полностью без ручного редактирования конфигурационных файлов.

**Технический подход**: Расширение существующей модели Source типом `jira`, динамическая генерация Meltano конфигурации, использование tap-jira extractor с поддержкой incremental replication.

---

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI 0.109+, SQLAlchemy 2.0 (async), React 18, Meltano 3.x, tap-jira
**Storage**: PostgreSQL 15+ (System DB for config, Business DB for extracted data)
**Testing**: pytest + pytest-asyncio (backend), Vitest + React Testing Library (frontend)
**Target Platform**: Linux server (Docker containers)
**Project Type**: Web application (backend API + frontend SPA)
**Performance Goals**: Preview completes in ≤30s for 100 records; Full sync handles 10k issues
**Constraints**: No JQL support (tap limitation); OAuth auth deferred to Phase 2
**Scale/Scope**: Single tenant; 1-5 Jira sources per tenant; 100k-1M issues per source

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Security-First Credential Management** | ✅ PASS | API token stored encrypted in `source_credentials` table (existing pattern) |
| **II. Meltano-First Data Integration** | ✅ PASS | Using tap-jira Meltano extractor; no custom connectors |
| **III. Dual-Database Separation** | ✅ PASS | Credentials in System DB; extracted data in Business DB |
| **IV. API-First Backend Architecture** | ✅ PASS | All functionality via `/api/v1/sources/*/jira/*` endpoints |
| **V. Containerized Deployment** | ✅ PASS | tap-jira runs in Meltano container; no new services |
| **VI. Observable Pipelines** | ✅ PASS | Meltano logs captured; run metrics tracked in existing `runs` table |
| **VII. UI-Consistent Connector Experience** | ✅ PASS | Same UX flow: Credentials → Settings → Preview → Create Flow |

**Gate Result**: ✅ All principles satisfied. No violations to justify.

---

## Project Structure

### Documentation (this feature)

```text
specs/003-jira-connector/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 research output
├── data-model.md        # Data model extensions
├── quickstart.md        # Developer quickstart guide
└── contracts/
    └── api.md           # API contract definitions
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── models/
│   │   └── source.py              # Add extraction_config field
│   ├── api/
│   │   └── v1/
│   │       ├── sources.py         # Extend for Jira source type
│   │       └── jira.py            # NEW: Jira-specific endpoints
│   ├── services/
│   │   ├── source_service.py      # Extend for Jira validation
│   │   ├── jira_service.py        # NEW: Jira API client
│   │   └── meltano.py             # Extend for tap-jira config
│   └── schemas/
│       └── jira.py                # NEW: Pydantic schemas for Jira
├── migrations/
│   └── versions/
│       └── XXX_add_extraction_config.py  # NEW migration
└── tests/
    ├── unit/
    │   └── test_jira_service.py   # NEW
    └── integration/
        └── test_jira_endpoints.py # NEW

frontend/
├── src/
│   ├── pages/
│   │   └── Sources/
│   │       └── SourceForm.tsx     # Extend for Jira type
│   ├── components/
│   │   └── JiraConfig/
│   │       ├── JiraCredentialsForm.tsx    # NEW
│   │       ├── JiraStreamSelector.tsx     # NEW
│   │       └── JiraPreviewResults.tsx     # NEW
│   └── services/
│       └── jiraApi.ts             # NEW: Jira API client
└── tests/
    └── components/
        └── JiraConfig.test.tsx    # NEW

meltano/
├── meltano.yml                    # Add tap-jira extractor config
└── plugins/
    └── extractors/
        └── tap-jira/              # NEW: tap-jira installation
```

**Structure Decision**: Extend existing web application structure. Backend adds Jira-specific service layer and API endpoints. Frontend adds Jira configuration components. Meltano adds tap-jira extractor.

---

## Implementation Phases

### Phase 1: Backend Foundation

**Goal**: Extend backend to support Jira source type with credentials and validation.

**Tasks**:
1. Add `extraction_config` JSONB field to `sources` table
2. Create `JiraService` for Jira REST API interaction
3. Extend `SourceService` to validate Jira credentials
4. Add Jira-specific error classification

**Deliverable**: `POST /api/v1/sources` with `source_type: jira` works and validates credentials.

---

### Phase 2: Jira API Endpoints

**Goal**: Expose Jira-specific functionality via REST API.

**Tasks**:
1. Create `/api/v1/sources/{id}/jira/projects` endpoint
2. Create `/api/v1/sources/{id}/jira/streams` endpoint
3. Create `/api/v1/sources/{id}/jira/streams/{name}/schema` endpoint
4. Create `/api/v1/sources/{id}/extraction-config` endpoint
5. Create Pydantic schemas for all Jira endpoints

**Deliverable**: All Jira metadata endpoints return correct data.

---

### Phase 3: Preview Integration

**Goal**: Enable preview functionality for Jira sources.

**Tasks**:
1. Create `/api/v1/sources/{id}/jira/preview` endpoint
2. Extend `MeltanoService` to generate tap-jira config
3. Implement preview execution via Meltano
4. Handle preview errors with classification
5. Store preview results in `preview_sessions` table

**Deliverable**: Preview returns sample records and schema for Jira data.

---

### Phase 4: Frontend - Source Form

**Goal**: Extend source creation form for Jira type.

**Tasks**:
1. Add "Jira" option to source type dropdown
2. Create `JiraCredentialsForm` component
3. Implement conditional field rendering (URL, Email, Token)
4. Add credential validation on save
5. Implement draft saving

**Deliverable**: Users can create Jira sources through UI.

---

### Phase 5: Frontend - Extraction Config

**Goal**: UI for configuring Jira extraction settings.

**Tasks**:
1. Create `JiraStreamSelector` component
2. Load and display available projects
3. Implement stream selection with dependency handling
4. Add incremental configuration toggle
5. Add start date picker

**Deliverable**: Users can configure extraction settings through UI.

---

### Phase 6: Frontend - Preview

**Goal**: UI for previewing Jira data.

**Tasks**:
1. Create `JiraPreviewResults` component
2. Implement preview trigger button
3. Display sample records in table
4. Show schema information
5. Handle and display errors with classification

**Deliverable**: Users can preview Jira data before creating flow.

---

### Phase 7: Meltano Integration

**Goal**: Configure and test Meltano tap-jira extraction.

**Tasks**:
1. Install tap-jira in Meltano project
2. Create dynamic config generation
3. Test incremental replication
4. Verify state management
5. Document batch size tuning

**Deliverable**: Full flow execution works end-to-end.

---

### Phase 8: Testing & Documentation

**Goal**: Ensure quality and provide user documentation.

**Tasks**:
1. Unit tests for JiraService
2. Integration tests for Jira endpoints
3. E2E test for full UI flow
4. Update user documentation
5. Add inline code comments

**Deliverable**: All tests pass; documentation complete.

---

## Dependencies

### External Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| tap-jira | latest | Meltano extractor for Jira |
| httpx | ^0.27 | HTTP client for Jira REST API |

### Internal Dependencies

| Component | Dependency | Reason |
|-----------|------------|--------|
| JiraService | SourceService | Uses existing source validation pattern |
| JiraEndpoints | AuthService | Requires authentication middleware |
| PreviewEndpoint | MeltanoService | Executes tap-jira via Meltano |
| Frontend | React Query | Uses existing data fetching pattern |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| tap-jira API incompatibility | Medium | High | Test with real Jira instance early |
| Jira rate limiting | High | Medium | Implement batch size tuning; add retry logic |
| No JQL support limitation | Medium | Medium | Document clearly; suggest SQL filtering |
| OAuth2 requirement | Low | Low | Defer to Phase 2; Basic Auth sufficient for MVP |

---

## Rollout Plan

### Stage 1: Internal Testing
- Deploy to development environment
- Test with internal Jira instance
- Validate all user stories

### Stage 2: Beta
- Enable via feature flag `jira_connector_enabled`
- Limited rollout to 2-3 beta users
- Collect feedback

### Stage 3: General Availability
- Remove feature flag
- Update documentation
- Announce availability

---

## Success Criteria

| Criterion | Metric | Validation |
|-----------|--------|------------|
| SC-001 | Source creation ≤3 min | User testing |
| SC-002 | 95% first-attempt validation | Analytics |
| SC-003 | Preview ≤30s | Performance testing |
| SC-004 | 100% error classification | Code review |
| SC-005 | Flow execution success | Integration tests |
| SC-006 | Incremental replication works | E2E test |
| SC-007 | No regressions in postgres/s3 | Regression test suite |
