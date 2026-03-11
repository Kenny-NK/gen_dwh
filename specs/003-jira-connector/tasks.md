# Tasks: Jira Source Connector

**Input**: Design documents from `/specs/003-jira-connector/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Meltano & Infrastructure)

**Purpose**: Install dependencies and prepare infrastructure for Jira connector.

- [ ] T001 Install tap-jira extractor in meltano project via `meltano add extractor tap-jira`
- [ ] T002 [P] Add httpx dependency to backend pyproject.toml for Jira REST API client
- [ ] T003 [P] Create migration to add extraction_config JSONB field to sources table in backend/migrations/versions/011_add_extraction_config_to_sources.py
- [ ] T004 Run migration and verify schema update in System PostgreSQL

---

## Phase 2: Foundational (Backend Core)

**Purpose**: Core backend infrastructure that MUST be complete before ANY user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T005 Add extraction_config JSONB field to Source model in backend/src/models/source.py
- [ ] T006 [P] Create JiraExtractionConfig Pydantic schema in backend/src/schemas/jira.py
- [ ] T007 [P] Create JiraStreamMetadata Pydantic schema in backend/src/schemas/jira.py
- [ ] T008 [P] Create JiraErrorResponse Pydantic schema in backend/src/schemas/jira.py
- [ ] T009 Create JiraService class with HTTP client initialization in backend/src/services/jira_service.py
- [ ] T010 Add validate_jira_credentials method to JiraService in backend/src/services/jira_service.py
- [ ] T011 Add get_projects method to JiraService in backend/src/services/jira_service.py
- [ ] T012 Add get_streams method to JiraService in backend/src/services/jira_service.py
- [ ] T013 Add classify_error static method to JiraService for error classification in backend/src/services/jira_service.py
- [ ] T014 Extend SourceService._validate_source to handle source_type='jira' in backend/src/services/source_service.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Подключение Jira Source (Priority: P1) 🎯 MVP

**Goal**: Пользователь создаёт новый источник типа Jira, вводит credentials и получает подтверждение успешного подключения.

**Independent Test**: Пользователь создаёт Jira source с валидными credentials и видит статус "connected".

### Backend Implementation for US1

- [ ] T015 [P] [US1] Create POST /api/v1/sources endpoint handler for jira source_type in backend/src/api/v1/sources.py
- [ ] T016 [P] [US1] Create PATCH /api/v1/sources/{id} endpoint handler for jira updates in backend/src/api/v1/sources.py
- [ ] T017 [P] [US1] Create POST /api/v1/sources/{id}/test endpoint for connection testing in backend/src/api/v1/sources.py
- [ ] T018 [US1] Add Jira source type validation (HTTPS URL, email format) in backend/src/services/source_service.py
- [ ] T019 [US1] Add Jira credentials encryption/decryption integration in backend/src/services/source_service.py

### Frontend Implementation for US1

- [ ] T020 [P] [US1] Add "jira" option to source_type enum in frontend/src/pages/Sources/SourceForm.tsx
- [ ] T021 [P] [US1] Create conditional field rendering for Jira (Base URL, Email, API Token) in frontend/src/pages/Sources/SourceForm.tsx
- [ ] T022 [US1] Add Jira-specific form validation schema with Zod in frontend/src/pages/Sources/SourceForm.tsx
- [ ] T023 [US1] Implement API token masking in password field display in frontend/src/pages/Sources/SourceForm.tsx
- [ ] T024 [US1] Add connection test mutation with error display in frontend/src/pages/Sources/SourceForm.tsx

**Checkpoint**: At this point, User Story 1 should be fully functional - users can create Jira sources through UI

---

## Phase 4: User Story 2 - Настройка параметров извлечения (Priority: P1)

**Goal**: Пользователь выбирает проекты, сущности и фильтры для извлечения данных из Jira.

**Independent Test**: Пользователь выбирает конкретные проекты и streams, система сохраняет конфигурацию.

### Backend Implementation for US2

- [ ] T025 [P] [US2] Create GET /api/v1/sources/{id}/jira/projects endpoint in backend/src/api/v1/jira.py
- [ ] T026 [P] [US2] Create GET /api/v1/sources/{id}/jira/streams endpoint in backend/src/api/v1/jira.py
- [ ] T027 [P] [US2] Create GET /api/v1/sources/{id}/jira/streams/{name}/schema endpoint in backend/src/api/v1/jira.py
- [ ] T028 [US2] Create PATCH /api/v1/sources/{id}/extraction-config endpoint in backend/src/api/v1/jira.py
- [ ] T029 [US2] Add stream dependency validation logic in backend/src/services/jira_service.py
- [ ] T030 [US2] Add extraction config update handler in backend/src/services/source_service.py

### Frontend Implementation for US2

- [ ] T031 [P] [US2] Create frontend/src/services/jiraApi.ts with API client functions
- [ ] T032 [P] [US2] Create JiraStreamSelector component in frontend/src/components/JiraConfig/JiraStreamSelector.tsx
- [ ] T033 [US2] Add project multi-select dropdown in JiraStreamSelector component
- [ ] T034 [US2] Add stream checkboxes with dependency auto-selection in JiraStreamSelector component
- [ ] T035 [US2] Add incremental toggle and start date picker in JiraStreamSelector component
- [ ] T036 [US2] Add batch size input field in JiraStreamSelector component
- [ ] T037 [US2] Add save draft mutation in JiraStreamSelector component

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Preview данных (Priority: P1)

**Goal**: Пользователь запускает preview для проверки данных перед созданием потока.

**Independent Test**: Пользователь запускает preview и видит sample records с корректными данными.

### Backend Implementation for US3

- [ ] T038 [P] [US3] Create POST /api/v1/sources/{id}/jira/preview endpoint in backend/src/api/v1/jira.py
- [ ] T039 [US3] Add generate_tap_jira_config method to MeltanoService in backend/src/services/meltano.py
- [ ] T040 [US3] Add run_preview method to MeltanoService for tap-jira execution in backend/src/services/meltano.py
- [ ] T041 [US3] Add preview result parsing and schema extraction in backend/src/services/jira_service.py
- [ ] T042 [US3] Add preview error classification and user-friendly messages in backend/src/services/jira_service.py
- [ ] T043 [US3] Store preview results in preview_sessions table in backend/src/services/preview.py

### Frontend Implementation for US3

- [ ] T044 [P] [US3] Create JiraPreviewResults component in frontend/src/components/JiraConfig/JiraPreviewResults.tsx
- [ ] T045 [US3] Add preview trigger button with loading state in JiraPreviewResults component
- [ ] T046 [US3] Add sample records table display in JiraPreviewResults component
- [ ] T047 [US3] Add schema view (fields and types) in JiraPreviewResults component
- [ ] T048 [US3] Add error display with classification (auth/network/config/runtime) in JiraPreviewResults component
- [ ] T049 [US3] Add "Create Flow" button on successful preview in JiraPreviewResults component

**Checkpoint**: At this point, User Stories 1, 2 AND 3 should all work independently

---

## Phase 6: User Story 4 - Создание потока (Priority: P2)

**Goal**: Пользователь создаёт поток для регулярной загрузки данных из Jira.

**Independent Test**: Пользователь создаёт поток, запускает его и видит данные в целевой таблице.

### Backend Implementation for US4

- [ ] T050 [P] [US4] Extend FlowService to support Jira source_type in backend/src/services/flow_service.py
- [ ] T051 [US4] Add generate_meltano_config_for_jira_flow method in backend/src/services/meltano.py
- [ ] T052 [US4] Add state file path handling for Jira incremental replication in backend/src/services/meltano.py
- [ ] T053 [US4] Ensure Jira flows work with existing scheduler in backend/src/services/scheduler.py

### Frontend Implementation for US4

- [ ] T054 [P] [US4] Extend FlowCreate wizard to pre-populate from Jira preview in frontend/src/pages/Flows/FlowCreate.tsx
- [ ] T055 [US4] Add Jira-specific flow table configuration UI in frontend/src/pages/Flows/FlowCreate.tsx
- [ ] T056 [US4] Add replication mode selection (full/incremental) for Jira streams in frontend/src/pages/Flows/FlowCreate.tsx

**Checkpoint**: At this point, User Stories 1-4 should all work independently

---

## Phase 7: User Story 5 - Управление существующим Jira Source (Priority: P2)

**Goal**: Пользователь редактирует, тестирует и удаляет Jira source.

**Independent Test**: Пользователь изменяет токен, тестирует подключение и видит актуальный статус.

### Backend Implementation for US5

- [ ] T057 [P] [US5] Add credential masking in source detail response in backend/src/api/v1/sources.py
- [ ] T058 [US5] Add deletion guard for Jira sources with active flows in backend/src/services/source_service.py
- [ ] T059 [US5] Add audit logging for credential changes in backend/src/services/source_service.py

### Frontend Implementation for US5

- [ ] T060 [P] [US5] Add masked token display (last 4 chars only) in frontend/src/pages/Sources/SourceForm.tsx
- [ ] T061 [US5] Add "Test Connection" button in edit mode in frontend/src/pages/Sources/SourceForm.tsx
- [ ] T062 [US5] Add deletion confirmation with active flows warning in frontend/src/pages/Sources/SourcesList.tsx

**Checkpoint**: All user stories should now be independently functional

---

## Phase 8: Meltano Integration & Testing

**Purpose**: Full Meltano integration and test coverage.

- [ ] T063 Create dynamic meltano.yml generation for tap-jira in backend/src/services/meltano.py
- [ ] T064 Test incremental replication state persistence in Meltano
- [ ] T065 [P] Create unit tests for JiraService in backend/tests/unit/test_jira_service.py
- [ ] T066 [P] Create integration tests for Jira endpoints in backend/tests/integration/test_jira_endpoints.py
- [ ] T067 [P] Create frontend component tests in frontend/tests/components/JiraConfig.test.tsx
- [ ] T068 Verify existing postgres/s3 connectors still work (regression test)

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories.

- [ ] T069 [P] Add Jira connector documentation in docs/connectors/jira.md
- [ ] T070 [P] Add inline code comments for complex Jira logic
- [ ] T071 Add feature flag jira_connector_enabled support in backend/src/core/config.py
- [ ] T072 Update quickstart.md with actual tested commands in specs/003-jira-connector/quickstart.md
- [ ] T073 Performance test preview with 100 records and verify ≤30s response

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - US1 can start after Phase 2
  - US2 can start after Phase 2 (independent of US1)
  - US3 can start after Phase 2 (independent of US1, US2)
  - US4 can start after Phase 2 (uses existing flow infrastructure)
  - US5 can start after Phase 2 (extends US1 components)
- **Meltano Integration (Phase 8)**: Depends on US1-US3 completion
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Phase 2 - No dependencies on other stories
- **User Story 3 (P1)**: Can start after Phase 2 - No dependencies on other stories
- **User Story 4 (P2)**: Can start after Phase 2 - Uses existing flow infrastructure
- **User Story 5 (P2)**: Can start after Phase 2 - Extends US1 components but independently testable

### Within Each User Story

- Backend tasks before frontend tasks
- Models/schemas before services
- Services before endpoints
- Core implementation before integration

### Parallel Opportunities

- All Setup tasks (T001-T004) can run in parallel
- All Foundational schema tasks (T006-T008) can run in parallel
- Within each user story, backend [P] tasks can run in parallel
- Frontend [P] tasks can run in parallel within each story
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all backend tasks for US1 together:
Task: T015 - Create POST sources endpoint
Task: T016 - Create PATCH sources endpoint
Task: T017 - Create POST test endpoint

# After backend complete, launch all frontend tasks:
Task: T020 - Add jira option to source_type
Task: T021 - Create conditional field rendering
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Jira Source Creation)
4. Complete Phase 4: User Story 2 (Extraction Config)
5. Complete Phase 5: User Story 3 (Preview)
6. **STOP and VALIDATE**: Test US1-US3 independently
7. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Add User Story 4 → Test independently → Deploy/Demo
6. Add User Story 5 → Test independently → Deploy/Demo
7. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Backend)
   - Developer B: User Story 1 (Frontend)
   - Developer C: User Story 2 (Backend)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
