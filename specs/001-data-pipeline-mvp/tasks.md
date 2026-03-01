# Tasks: Data Pipeline MVP (PostgreSQL to PostgreSQL)

**Input**: Design documents from `/specs/001-data-pipeline-mvp/`
**Prerequisites**: plan.md (required), spec.md (required), data-model.md, contracts/, research.md, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Project Infrastructure)

**Purpose**: Initialize project structure, dependencies, and Docker environment

- [x] T001 Create project directory structure per plan.md (backend/, frontend/, docker/, meltano/)
- [x] T002 Initialize backend Python project with pyproject.toml in backend/
- [x] T003 [P] Initialize frontend React project with Vite in frontend/
- [x] T004 [P] Create Docker Compose files in docker/docker-compose.yml and docker/docker-compose.dev.yml
- [x] T005 [P] Create environment template in docker/.env.example
- [x] T006 [P] Configure backend linting (ruff) and formatting in backend/pyproject.toml
- [x] T007 [P] Configure frontend linting (ESLint) in frontend/eslint.config.js
- [x] T008 Initialize Meltano project in meltano/ with meltano.yml
- [x] T009 Install Meltano tap-postgres extractor in meltano/
- [x] T010 Install Meltano target-postgres loader in meltano/

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Database & Migrations

- [x] T011 Create Alembic migration structure in backend/migrations/
- [x] T012 Create Tenant model and table in public schema in backend/src/models/tenant.py
- [x] T013 Create User model and table in public schema in backend/src/models/user.py
- [x] T014 Create initial migration for public schema (tenants, users) in backend/migrations/versions/

### Core Configuration & Security

- [x] T015 [P] Create application configuration module in backend/src/core/config.py
- [x] T016 [P] Create security utilities (password hashing, JWT validation) in backend/src/core/security.py
- [x] T017 Create tenant context management middleware in backend/src/core/tenant.py
- [x] T018 [P] Create database dependency with tenant schema switching in backend/src/api/deps.py

### Authentication & Authorization

- [x] T019 Implement Keycloak OIDC client in backend/src/core/auth.py
- [x] T020 Create authentication middleware with JWT validation in backend/src/middleware/auth.py
- [x] T021 [P] Create role-based permission system in backend/src/core/permissions.py
- [x] T022 Create /auth/me endpoint in backend/src/api/v1/auth.py

### API Infrastructure

- [x] T023 Create main FastAPI application in backend/src/main.py
- [x] T024 Create API router with versioning in backend/src/api/router.py
- [x] T025 [P] Create health check endpoint in backend/src/api/health.py
- [x] T026 Configure OpenAPI documentation in backend/src/main.py

### Frontend Foundation

- [x] T027 Create API client module with auth interceptors in frontend/src/services/api.ts
- [x] T028 [P] Create authentication hooks (useAuth) in frontend/src/hooks/useAuth.ts
- [x] T029 [P] Create common UI components (Button, Input, Modal, Table) in frontend/src/components/common/
- [x] T030 Create layout component with navigation in frontend/src/components/Layout.tsx
- [x] T031 Configure React Router with protected routes in frontend/src/main.tsx

### Celery & Scheduler Setup

- [x] T032 Create Celery app configuration in backend/src/core/celery_app.py
- [x] T033 [P] Create Redis connection module in backend/src/core/redis.py
- [x] T034 Configure Celery Beat for scheduled tasks in backend/src/core/scheduler.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Подключение источника (Priority: P1) 🎯 MVP

**Goal**: Пользователь добавляет источник PostgreSQL, проходит проверку подключения и получает понятный результат

**Independent Test**: Пользователь создает источник с валидными и невалидными параметрами и получает корректный исход (успех/ошибка)

### Backend Implementation for US1

- [x] T035 [P] [US1] Create Source model (tenant schema) in backend/src/models/source.py
- [x] T036 [P] [US1] Create SourceCredential model with encryption in backend/src/models/source_credential.py
- [x] T037 [US1] Create database migration for sources and source_credentials tables in backend/migrations/versions/
- [x] T038 [US1] Create connection testing service in backend/src/services/connection.py
- [x] T039 [US1] Implement credential encryption/decryption with pgcrypto in backend/src/services/connection.py
- [x] T040 [US1] Create SourceService with CRUD operations in backend/src/services/source_service.py
- [x] T041 [US1] Create sources API endpoints (list, create, get, update, delete) in backend/src/api/v1/sources.py
- [x] T042 [US1] Implement connection test endpoint POST /sources/{id}/test in backend/src/api/v1/sources.py
- [x] T043 [US1] Create schema discovery endpoint GET /sources/{id}/schemas in backend/src/api/v1/sources.py
- [x] T044 [US1] Create table discovery endpoint GET /sources/{id}/schemas/{schema}/tables in backend/src/api/v1/sources.py

### Frontend Implementation for US1

- [x] T045 [P] [US1] Create Sources list page in frontend/src/pages/Sources/SourcesList.tsx
- [x] T046 [P] [US1] Create Source form component (create/edit) in frontend/src/pages/Sources/SourceForm.tsx
- [x] T047 [US1] Create connection status indicator component in frontend/src/components/ConnectionStatus.tsx
- [x] T048 [US1] Implement source creation with connection test in frontend/src/pages/Sources/SourceForm.tsx
- [x] T049 [US1] Add source edit functionality with re-validation in frontend/src/pages/Sources/SourceForm.tsx
- [x] T050 [US1] Implement source delete with confirmation in frontend/src/pages/Sources/SourcesList.tsx

**Checkpoint**: User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Настройка потока и preview (Priority: P1)

**Goal**: Пользователь выбирает источник, таблицы и режим загрузки, затем проверяет данные в preview до сохранения потока

**Independent Test**: Пользователь настраивает поток и подтверждает в preview, что данные соответствуют ожиданиям

### Backend Implementation for US2

- [x] T051 [P] [US2] Create Flow model (tenant schema) in backend/src/models/flow.py
- [x] T052 [P] [US2] Create FlowTable model in backend/src/models/flow_table.py
- [x] T053 [P] [US2] Create PreviewSession model in backend/src/models/preview_session.py
- [x] T054 [US2] Create database migration for flows, flow_tables, preview_sessions in backend/migrations/versions/
- [x] T055 [US2] Create PII detection service in backend/src/services/masking.py
- [x] T056 [US2] Create preview execution service in backend/src/services/preview.py
- [x] T057 [US2] Implement Meltano dry-run for preview in backend/src/services/preview.py
- [x] T058 [US2] Create FlowService with CRUD operations in backend/src/services/flow_service.py
- [x] T059 [US2] Create flows API endpoints in backend/src/api/v1/flows.py
- [x] T060 [US2] Create flow tables endpoints (add, update, remove table) in backend/src/api/v1/flows.py
- [x] T061 [US2] Create preview API endpoints (start, status, data, schema) in backend/src/api/v1/preview.py
- [x] T062 [US2] Implement data masking for User role in preview responses in backend/src/services/masking.py

### Frontend Implementation for US2

- [x] T063 [P] [US2] Create FlowWizard component with steps in frontend/src/components/FlowWizard/FlowWizard.tsx
- [x] T064 [P] [US2] Create SourceStep component (select source) in frontend/src/components/FlowWizard/SourceStep.tsx
- [x] T065 [P] [US2] Create TableSelectionStep component in frontend/src/components/FlowWizard/TableSelectionStep.tsx
- [x] T066 [P] [US2] Create TableConfigStep component (replication method, cursor field) in frontend/src/components/FlowWizard/TableConfigStep.tsx
- [x] T067 [US2] Create Preview component with table viewer in frontend/src/components/Preview/Preview.tsx
- [x] T068 [US2] Implement preview pagination, sorting, filtering in frontend/src/components/Preview/Preview.tsx
- [x] T069 [US2] Create masked value display component in frontend/src/components/Preview/MaskedValue.tsx
- [x] T070 [US2] Create Flows list page in frontend/src/pages/Flows/FlowsList.tsx
- [x] T071 [US2] Create Flow detail/edit page in frontend/src/pages/Flows/FlowDetail.tsx

**Checkpoint**: User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Target, расписание и первый запуск (Priority: P1)

**Goal**: Пользователь задает target-настройки, расписание, сохраняет поток и получает результат первого запуска

**Independent Test**: Пользователь сохраняет поток, запускает его и проверяет, что данные появились в target согласно настройкам

### Backend Implementation for US3

- [x] T072 [P] [US3] Create Run model in backend/src/models/run.py
- [x] T073 [P] [US3] Create Schedule model in backend/src/models/schedule.py
- [x] T074 [US3] Create database migration for runs and schedules in backend/migrations/versions/
- [x] T075 [US3] Create Meltano orchestration service in backend/src/services/meltano.py
- [x] T076 [US3] Implement flow execution Celery task in backend/src/services/scheduler.py
- [x] T077 [US3] Implement advisory lock for concurrent run prevention in backend/src/services/scheduler.py
- [x] T078 [US3] Implement retry policy (5 attempts) in backend/src/services/scheduler.py
- [x] T079 [US3] Create RunService in backend/src/services/run_service.py
- [x] T080 [US3] Create ScheduleService in backend/src/services/schedule_service.py
- [x] T081 [US3] Create runs API endpoints in backend/src/api/v1/runs.py
- [x] T082 [US3] Create schedules API endpoints in backend/src/api/v1/schedules.py
- [x] T083 [US3] Implement flow activate endpoint (draft → paused) in backend/src/api/v1/flows.py
- [x] T084 [US3] Implement flow pause/resume endpoints in backend/src/api/v1/flows.py
- [x] T085 [US3] Implement manual run trigger endpoint in backend/src/api/v1/runs.py
- [x] T086 [US3] Implement run cancellation endpoint in backend/src/api/v1/runs.py
- [x] T087 [US3] Create cron expression validation in backend/src/services/schedule_service.py
- [x] T088 [US3] Configure Celery Beat schedule from database in backend/src/core/scheduler.py

### Frontend Implementation for US3

- [x] T089 [P] [US3] Create TargetConfigStep component in frontend/src/components/FlowWizard/TargetConfigStep.tsx
- [x] T090 [P] [US3] Create ScheduleStep component in frontend/src/components/FlowWizard/ScheduleStep.tsx
- [x] T091 [P] [US3] Create cron expression builder/validator in frontend/src/components/ScheduleBuilder.tsx
- [x] T092 [US3] Create flow activation UI in frontend/src/pages/Flows/FlowDetail.tsx
- [x] T093 [US3] Create run trigger button with confirmation in frontend/src/pages/Flows/FlowDetail.tsx
- [x] T094 [US3] Create RunStatus component with progress in frontend/src/components/RunStatus.tsx
- [x] T095 [US3] Create Runs history page in frontend/src/pages/Runs/RunsList.tsx
- [x] T096 [US3] Create Run detail page with logs in frontend/src/pages/Runs/RunDetail.tsx

**Checkpoint**: All P1 user stories should now be independently functional

---

## Phase 6: User Story 4 - Мониторинг и управление (Priority: P2)

**Goal**: Пользователь на главной странице видит потоки, источники, статусы, историю запусков и может управлять жизненным циклом

**Independent Test**: Пользователь видит актуальные статусы, историю и может перейти к проблемному потоку для исправления

### Backend Implementation for US4

- [x] T097 [P] [US4] Create Notification model in backend/src/models/notification.py
- [x] T098 [P] [US4] Create AuditEvent model in backend/src/models/audit.py
- [x] T099 [US4] Create database migration for notifications and audit_events in backend/migrations/versions/
- [x] T100 [US4] Create NotificationService in backend/src/services/notification_service.py
- [x] T101 [US4] Create AuditService with logging in backend/src/services/audit_service.py
- [x] T102 [US4] Integrate audit logging into source/flow/run operations in backend/src/services/
- [x] T103 [US4] Create notifications API endpoints in backend/src/api/v1/notifications.py
- [x] T104 [US4] Create audit API endpoints (admin only) in backend/src/api/v1/audit.py
- [x] T105 [US4] Create dashboard stats endpoint in backend/src/api/v1/dashboard.py
- [x] T106 [US4] Implement notification creation on run completion/failure in backend/src/services/scheduler.py

### Frontend Implementation for US4

- [x] T107 [P] [US4] Create Dashboard page with stats in frontend/src/pages/Dashboard/Dashboard.tsx
- [x] T108 [P] [US4] Create flows list widget for dashboard in frontend/src/pages/Dashboard/FlowsWidget.tsx
- [x] T109 [P] [US4] Create sources list widget for dashboard in frontend/src/pages/Dashboard/SourcesWidget.tsx
- [x] T110 [P] [US4] Create runs history widget for dashboard in frontend/src/pages/Dashboard/RunsWidget.tsx
- [x] T111 [US4] Create notification bell component in frontend/src/components/Notifications/NotificationBell.tsx
- [x] T112 [US4] Create notification dropdown/list in frontend/src/components/Notifications/NotificationList.tsx
- [x] T113 [US4] Create audit log page (admin) in frontend/src/pages/Audit/AuditLog.tsx
- [x] T114 [US4] Implement flow status badges in frontend/src/components/FlowStatusBadge.tsx
- [x] T115 [US4] Create quick actions (Create Flow, Connect Source) on dashboard in frontend/src/pages/Dashboard/Dashboard.tsx

**Checkpoint**: All user stories should now be independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T116 [P] Add error boundary component in frontend/src/components/ErrorBoundary.tsx
- [x] T117 [P] Add loading states and skeletons in frontend/src/components/common/LoadingStates.tsx
- [x] T118 [P] Add toast notification system in frontend/src/components/common/Toast.tsx
- [x] T119 [P] Create audit retention cleanup task in backend/src/tasks/cleanup.py
- [x] T120 [P] Add request validation error handling in backend/src/middleware/error_handler.py
- [x] T121 [P] Add API rate limiting in backend/src/middleware/rate_limit.py
- [x] T122 Create Dockerfile for backend in backend/Dockerfile
- [x] T123 [P] Create Dockerfile for frontend in frontend/Dockerfile
- [x] T124 [P] Create Dockerfile for Celery worker in docker/worker.Dockerfile
- [x] T125 Configure production Docker Compose in docker/docker-compose.yml
- [x] T126 [P] Add structured logging configuration in backend/src/core/logging.py
- [x] T127 [P] Add metrics collection endpoint in backend/src/api/metrics.py
- [x] T128 Create database seed script for testing in backend/scripts/seed.py
- [x] T129 [P] Verify quickstart.md steps work end-to-end

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 can proceed independently
  - US2 depends on US1 models (Source) but can start in parallel on non-dependent tasks
  - US3 depends on US1 and US2 models but can start in parallel on non-dependent tasks
  - US4 depends on all previous user stories for full functionality
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational - No dependencies on other stories
- **US2 (P1)**: Can start after Foundational - Uses Source model from US1
- **US3 (P1)**: Can start after Foundational - Uses Flow model from US2, Source from US1
- **US4 (P2)**: Can start after Foundational - Integrates with all previous stories

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Within each user story phase, tasks marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all models for US1 together:
T035: Create Source model in backend/src/models/source.py
T036: Create SourceCredential model in backend/src/models/source_credential.py

# Launch all frontend components for US1 together:
T045: Create Sources list page
T046: Create Source form component
T047: Create connection status indicator component
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 - Source connection
4. Complete Phase 4: User Story 2 - Flow configuration with preview
5. Complete Phase 5: User Story 3 - Target, schedule, and first run
6. **STOP and VALIDATE**: Test end-to-end flow (source → flow → run → data in target)
7. Deploy/demo if ready

### Full MVP Delivery

1. Complete MVP First steps above
2. Complete Phase 6: User Story 4 - Monitoring and management
3. Complete Phase 7: Polish & Cross-Cutting Concerns
4. Final validation of all user stories
5. Deploy to production

---

## Summary

| Category | Count |
|----------|-------|
| Total Tasks | 129 |
| Setup Phase | 10 |
| Foundational Phase | 24 |
| US1 - Source Connection | 16 |
| US2 - Flow & Preview | 21 |
| US3 - Target & Run | 26 |
| US4 - Monitoring | 19 |
| Polish Phase | 14 |
| Parallelizable Tasks | 52 |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
