# Implementation Plan: Data Pipeline MVP (PostgreSQL to PostgreSQL)

**Branch**: `001-data-pipeline-mvp` | **Date**: 2026-03-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-data-pipeline-mvp/spec.md`

## Summary

MVP для управления потоками данных PostgreSQL → PostgreSQL через Meltano. Система позволяет пользователям подключать источники данных, настраивать потоки загрузки с preview, запускать по расписанию и мониторить статусы. Технический подход: FastAPI backend + React frontend, multi-tenant изоляция через схемы PostgreSQL, Celery/Redis для scheduler, Keycloak OIDC для auth.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI 0.109+, Meltano 3.x, SQLAlchemy 2.0 (async), Celery + Redis, React 18 + Vite, Keycloak OIDC
**Storage**: PostgreSQL 15+ (System DB - metadata/credentials, Business DB - extracted data)
**Testing**: pytest + testcontainers (backend), Vitest + Playwright (frontend)
**Target Platform**: Linux server, Docker Compose deployment
**Project Type**: Self-hosted multi-tenant web application (backend + frontend)
**Performance Goals**: Первый запуск ≤1 час для 20GB, API p95 <500ms, preview ≤10k rows
**Constraints**: Один активный run на таблицу, retry 5 попыток, audit retention 100 дней
**Scale/Scope**: Medium client (~20GB source), multi-tenant, ~10 concurrent flows per tenant

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Security-First Credential Management | ✅ PASS | Credentials encrypted in System DB, never exposed in API responses |
| II. Meltano-First Data Integration | ✅ PASS | All connectors via Meltano tap-postgres → target-postgres |
| III. Dual-Database Separation | ✅ PASS | System DB (metadata) separate from Business DB (extracted data) |
| IV. API-First Backend Architecture | ✅ PASS | FastAPI with /api/v1/ versioning, OpenAPI docs |
| V. Containerized Deployment | ✅ PASS | Docker Compose with health checks for all services |
| VI. Observable Pipelines | ✅ PASS | Run history with metrics, structured logging, status queryable via API |

**Constitution Compliance**: All 6 principles satisfied. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/001-data-pipeline-mvp/
├── plan.md              # This file
├── research.md          # Phase 0: Technology decisions
├── data-model.md        # Phase 1: Entities and state transitions
├── quickstart.md        # Phase 1: Local development setup
├── contracts/           # Phase 1: API contracts
│   ├── auth.yaml        # Keycloak OIDC integration
│   ├── sources.yaml     # Source connection endpoints
│   ├── flows.yaml       # Data flow management
│   ├── runs.yaml        # Run execution and history
│   ├── preview.yaml     # Preview data endpoints
│   └── schedules.yaml   # Schedule configuration
└── tasks.md             # Phase 2: Implementation tasks
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── sources.py
│   │   │   ├── flows.py
│   │   │   ├── runs.py
│   │   │   ├── preview.py
│   │   │   ├── schedules.py
│   │   │   └── audit.py
│   │   ├── deps.py          # Dependencies (db, auth, tenant)
│   │   └── router.py
│   ├── models/
│   │   ├── tenant.py
│   │   ├── source.py
│   │   ├── flow.py
│   │   ├── run.py
│   │   ├── schedule.py
│   │   └── audit.py
│   ├── services/
│   │   ├── meltano.py       # Meltano orchestration
│   │   ├── connection.py    # DB connection testing
│   │   ├── preview.py       # Preview execution
│   │   ├── scheduler.py     # Celery tasks
│   │   └── masking.py       # PII detection/masking
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   └── tenant.py        # Tenant context management
│   └── main.py
├── migrations/
│   └── versions/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── pyproject.toml
└── Dockerfile

frontend/
├── src/
│   ├── pages/
│   │   ├── Dashboard.tsx
│   │   ├── Sources/
│   │   ├── Flows/
│   │   └── Runs/
│   ├── components/
│   │   ├── FlowWizard/
│   │   ├── Preview/
│   │   └── common/
│   ├── services/
│   │   └── api.ts
│   ├── hooks/
│   └── main.tsx
├── tests/
│   └── e2e/
├── package.json
├── vite.config.ts
└── Dockerfile

docker/
├── docker-compose.yml
├── docker-compose.dev.yml
└── .env.example

meltano/
├── meltano.yml
├── plugins/
│   └── extractors/tap-postgres/
└── loaders/target-postgres/
```

**Structure Decision**: Web application structure с отдельными backend и frontend директориями. Meltano конфигурация вынесена в отдельную директорию для изоляции pipeline кода.

## Complexity Tracking

> No constitution violations - table not required.

---

## Phase 0: Research Summary

See [research.md](./research.md) for detailed findings.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Meltano tap for PostgreSQL | tap-postgres (official) | Stable, well-documented, supports incremental via replication_key |
| Meltano target for PostgreSQL | target-postgres (MeltanoLabs) | Official, supports append/upsert/replace |
| Job scheduler | Celery + Redis beat | Integrates with FastAPI, supports retry, timezone-aware |
| Tenant isolation | Schema-per-tenant in System DB | Simple, PostgreSQL-native, clear data separation |
| Preview execution | Meltano dry-run to temp schema | Reuses Meltano infrastructure, no custom extraction code |
| PII detection | presidio-io + custom patterns | Industry-standard, configurable, Russian locale support |
| Secret encryption | PostgreSQL pgcrypto + AES-256 | Database-native, no external vault dependency for MVP |

---

## Phase 1: Design Artifacts

### Data Model

See [data-model.md](./data-model.md) for complete entity definitions.

### API Contracts

See [contracts/](./contracts/) for OpenAPI 3.0 specifications.

### Quick Start Guide

See [quickstart.md](./quickstart.md) for local development setup.

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Meltano tap-postgres connection issues | Connection test endpoint before save, detailed error messages |
| Preview memory overflow | Streaming execution, 10k row hard limit, pagination |
| Concurrent run conflicts | Database-level advisory lock per source_table identifier |
| Keycloak downtime | JWT validation caching, graceful degradation for read operations |
| Large data volume (20GB) | Chunked extraction in Meltano, progress tracking, resumable runs |
