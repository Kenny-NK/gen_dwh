# Feature Specification: Jira Source Connector (Meltano Tap)

**Feature Branch**: `003-jira-connector`
**Created**: 2026-03-05
**Status**: Draft
**Input**: Jira Source Connector (Meltano Tap) с полной настройкой через UI

## Overview

Добавление Jira-коннектора в существующую систему управления потоками данных. Пользователь должен иметь возможность подключить Jira как источник данных через UI, настроить параметры извлечения (проекты, сущности, фильтры), проверить данные через preview и создать поток для регулярной загрузки — полностью без ручного редактирования конфигурационных файлов.

---

## User Scenarios & Testing

### User Story 1 - Подключение Jira Source (Priority: P1)

Пользователь создаёт новый источник типа Jira, вводит credentials и получает подтверждение успешного подключения.

**Why this priority**: Без валидного подключения невозможно использовать Jira как источник данных.

**Independent Test**: Пользователь создаёт Jira source с валидными credentials и видит статус "connected".

**Acceptance Scenarios**:

1. **Given** пользователь на форме создания источника, **When** выбирает тип "Jira", **Then** видит поля: Base URL, Email, API Token.
2. **Given** пользователь ввёл валидные credentials (URL, email, token), **When** нажимает "Сохранить", **Then** система проверяет подключение к Jira API и сохраняет источник со статусом "connected".
3. **Given** пользователь ввёл неверные credentials, **When** нажимает "Сохранить", **Then** источник не сохраняется и показывается ошибка с классификацией (auth/network/config).
4. **Given** пользователь редактирует существующий Jira source, **When** изменяет токен, **Then** новый токен сохраняется в зашифрованном виде, старый перезаписывается.

---

### User Story 2 - Настройка параметров извлечения (Priority: P1)

Пользователь выбирает проекты, сущности и фильтры для извлечения данных из Jira.

**Why this priority**: Настройка параметров критична для получения релевантных данных.

**Independent Test**: Пользователь выбирает конкретные проекты и streams, система сохраняет конфигурацию.

**Acceptance Scenarios**:

1. **Given** валидный Jira source, **When** пользователь открывает настройки извлечения, **Then** видит список доступных проектов (загружается из Jira API).
2. **Given** пользователь выбрал проекты, **When** открывает список streams, **Then** видит доступные сущности: issues, users, projects, comments, worklogs.
3. **Given** пользователь настраивает инкрементальную загрузку, **When** выбирает stream "issues", **Then** видит опцию replication key (updated_since) и может задать начальную дату.
4. **Given** пользователь хочет отфильтровать issues, **When** вводит JQL-выражение, **Then** система валидирует синтаксис и сохраняет фильтр.
5. **Given** пользователь завершил настройку, **When** нажимает "Сохранить черновик", **Then** конфигурация сохраняется без запуска preview.

---

### User Story 3 - Preview данных (Priority: P1)

Пользователь запускает preview для проверки данных перед созданием потока.

**Why this priority**: Preview — ключевая ценность для валидации конфигурации без коммита в production.

**Independent Test**: Пользователь запускает preview и видит sample records с корректными данными.

**Acceptance Scenarios**:

1. **Given** настроенный Jira source с выбранными streams, **When** пользователь нажимает "Preview", **Then** система запускает тестовое извлечение через Meltano tap.
2. **Given** preview завершён успешно, **When** пользователь открывает результат, **Then** видит sample records (до 100 строк) и схему полей для каждого stream.
3. **Given** preview завершился ошибкой auth, **When** пользователь видит результат, **Then** отображается сообщение "Ошибка авторизации: проверьте API token".
4. **Given** preview завершился ошибкой network, **When** пользователь видит результат, **Then** отображается сообщение "Ошибка сети: проверьте Base URL и доступность Jira".
5. **Given** preview завершился ошибкой JQL, **When** пользователь видит результат, **Then** отображается сообщение с деталями синтаксической ошибки JQL.
6. **Given** в preview есть чувствительные данные (email, персональная информация), **When** пользователь роли User смотрит результат, **Then** значения маскированы.

---

### User Story 4 - Создание потока (Priority: P2)

Пользователь создаёт поток для регулярной загрузки данных из Jira.

**Why this priority**: После валидации через preview пользователь может создать production-поток.

**Independent Test**: Пользователь создаёт поток, запускает его и видит данные в целевой таблице.

**Acceptance Scenarios**:

1. **Given** успешный preview, **When** пользователь нажимает "Создать поток", **Then** открывается стандартный wizard создания потока с предзаполненными настройками.
2. **Given** пользователь завершил wizard, **When** сохраняет поток, **Then** поток создаётся со статусом "draft" или "paused".
3. **Given** поток создан, **When** пользователь запускает его вручную, **Then** система выполняет загрузку через Meltano и обновляет статус на "running" → "success"/"failed".
4. **Given** поток запущен по расписанию, **When** наступает время запуска, **Then** система выполняет загрузку с сохранением state для инкрементальной репликации.

---

### User Story 5 - Управление существующим Jira Source (Priority: P2)

Пользователь редактирует, тестирует и удаляет Jira source.

**Why this priority**: Операционное управление требуется для поддержки жизненного цикла.

**Independent Test**: Пользователь изменяет токен, тестирует подключение и видит актуальный статус.

**Acceptance Scenarios**:

1. **Given** существующий Jira source, **When** пользователь открывает карточку, **Then** видит все настройки (URL, email) с маскированным токеном.
2. **Given** пользователь изменил URL или токен, **When** нажимает "Проверить подключение", **Then** система выполняет тест API и показывает результат.
3. **Given** Jira source используется в активных потоках, **When** пользователь пытается удалить source, **Then** система блокирует удаление и показывает список связанных потоков.
4. **Given** Jira source не используется, **When** пользователь удаляет source, **Then** запись помечается deleted_at, credentials удаляются.

---

### Edge Cases

- Jira API возвращает rate limit (429) — система показывает ошибку и предлагает уменьшить batch size.
- Jira server недоступен (timeout) — система классифицирует как network error.
- JQL возвращает 0 результатов — preview показывает пустой результат с сообщением.
- Выбранный проект удалён из Jira — система показывает ошибку при preview/run.
- Token истёк (401) — система классифицирует как auth error, предлагает обновить credentials.
- Большой объём данных превышает лимит preview — система обрезает до 100 records.
- Инкрементальная загрузка без state — первый запуск делает full load.
- Конфликт расписания с активным запуском — система пропускает scheduled run.

---

## Requirements

### Functional Requirements

#### Source Type & Credentials

- **FR-001**: Система должна поддерживать новый тип источника `jira`.
- **FR-002**: Система должна позволять создавать Jira source с полями: base_url, email, api_token.
- **FR-003**: API token должен храниться в зашифрованном виде (как password для PostgreSQL source).
- **FR-004**: Система должна валидировать base_url как корректный HTTPS URL.
- **FR-005**: Система должна маскировать API token в UI (отображение только последних 4 символов).
- **FR-006**: Система должна поддерживать сохранение черновика настроек до валидации подключения.

#### Connection Validation

- **FR-007**: Система должна проверять подключение к Jira REST API при сохранении source.
- **FR-008**: Система должна классифицировать ошибки: auth (401/403), network (timeout/connection), config (invalid URL), runtime (5xx).
- **FR-009**: Система должна показывать информативные сообщения ошибок с рекомендациями по исправлению.

#### Extraction Settings

- **FR-010**: Система должна загружать список доступных проектов из Jira API для выбора пользователем.
- **FR-011**: Система должна поддерживать выбор streams: issues, users, projects, comments, worklogs.
- **FR-012**: Система должна позволять фильтровать issues через JQL-выражения.
- **FR-013**: Система должна валидировать JQL-синтаксис перед сохранением.
- **FR-014**: Система должна поддерживать инкрементальную загрузку с replication key (updated_since для issues).
- **FR-015**: Система должна позволять настраивать batch size / page size для API запросов.
- **FR-016**: Система должна сохранять настройки извлечения в конфигурации source/flow.

#### Preview

- **FR-017**: Система должна запускать preview через Meltano tap-jira в test режиме.
- **FR-018**: Preview должен возвращать до 100 sample records для каждого выбранного stream.
- **FR-019**: Preview должен показывать схему данных (поля, типы).
- **FR-020**: Preview должен маскировать PII для пользователей роли User.
- **FR-021**: Preview должен поддерживать повторный запуск с обновлёнными настройками.

#### Flow Creation

- **FR-022**: После успешного preview пользователь должен иметь возможность создать flow.
- **FR-023**: Wizard создания потока должен быть консистентен с другими коннекторами.
- **FR-024**: Поток должен поддерживать расписание (cron/interval/manual).
- **FR-025**: Поток должен поддерживать все write modes: append, upsert, replace.

#### Meltano Integration

- **FR-026**: Система должна использовать tap-jira Meltano extractor для извлечения данных.
- **FR-027**: Система должна генерировать meltano.yml конфигурацию динамически на основе настроек source.
- **FR-028**: Система должна сохранять state для инкрементальной репликации между запусками.
- **FR-029**: Логи Meltano не должны содержать секреты (token).

#### Non-Functional

- **FR-030**: Существующие коннекторы (postgres, s3) не должны быть затронуты изменениями.
- **FR-031**: Idempotent-сохранение конфигурации — повторное сохранение с теми же данными не создаёт дубликаты.
- **FR-032**: История изменений credentials должна аудироваться.

---

### Key Entities

- **JiraSource**: Расширение Source с полями base_url, email; тип `jira`.
- **JiraCredential**: API token в зашифрованном виде.
- **JiraExtractionConfig**: Настройки извлечения — projects, streams, jql_filters, replication_key, start_date, batch_size.
- **JiraStreamMetadata**: Метаданные stream — название, поля, типы, replication support.
- **PreviewSession**: Сессия preview с результатами для Jira source.

---

## UI Flow

```
Step 1: Create Source
├── Select type: Jira
├── Enter Base URL (e.g., https://company.atlassian.net)
├── Enter Email
├── Enter API Token (masked)
├── [Save Draft] or [Save & Validate]
└── → Status: connected / error

Step 2: Configure Extraction
├── Select Projects (multi-select, loaded from API)
├── Select Streams (issues, users, projects, comments, worklogs)
├── Configure Filters
│   ├── JQL expression (for issues)
│   ├── Date range (optional)
│   └── Batch size
├── Configure Incremental
│   ├── Toggle: Incremental load
│   ├── Replication key: updated_at
│   └── Start date
├── [Save Draft]
└── → Config saved

Step 3: Preview
├── [Run Preview]
├── Loading indicator
├── Results:
│   ├── Sample records table (max 100 rows)
│   ├── Schema view (fields, types)
│   └── Errors if any (classified)
├── [Re-run Preview] or [Create Flow]
└── → If success: proceed to Step 4

Step 4: Create Flow
├── Standard flow wizard (reuse existing)
├── Target schema/table configuration
├── Write mode selection
├── Schedule configuration
├── [Create Flow]
└── → Flow created in draft/paused status
```

---

## Data Model Extensions

### Source Table (existing)

```
source_type: 'postgres' | 's3' | 'jira'  -- add 'jira'
host: For Jira, stores base_url
port: For Jira, can be null or 443
database: For Jira, can be null
username: For Jira, stores email
```

### New: jira_extraction_config (JSON field or separate table)

```json
{
  "projects": ["PROJ1", "PROJ2"],
  "streams": ["issues", "users", "worklogs"],
  "jql_filters": {
    "issues": "project = PROJ1 AND updated > -30d"
  },
  "incremental": {
    "enabled": true,
    "replication_key": "updated",
    "start_date": "2026-01-01T00:00:00Z"
  },
  "batch_size": 100
}
```

---

## API Contracts

### Create Jira Source

```
POST /api/v1/sources
Content-Type: application/json

{
  "name": "My Jira",
  "source_type": "jira",
  "host": "https://company.atlassian.net",
  "port": 443,
  "database": "",
  "username": "user@example.com",
  "password": "API_TOKEN_HERE",
  "description": "Company Jira instance"
}

Response 201:
{
  "id": "uuid",
  "name": "My Jira",
  "source_type": "jira",
  "host": "https://company.atlassian.net",
  "username": "user@example.com",
  "connection_status": "connected",
  "created_at": "..."
}
```

### Get Available Projects

```
GET /api/v1/sources/{id}/jira/projects

Response 200:
{
  "projects": [
    {"key": "PROJ1", "name": "Project One"},
    {"key": "PROJ2", "name": "Project Two"}
  ]
}
```

### Get Available Streams

```
GET /api/v1/sources/{id}/jira/streams

Response 200:
{
  "streams": [
    {
      "name": "issues",
      "supported_replication_keys": ["updated", "created"],
      "fields": [
        {"name": "id", "type": "string"},
        {"name": "key", "type": "string"},
        {"name": "summary", "type": "string"},
        {"name": "status", "type": "string"},
        {"name": "updated", "type": "datetime"}
      ]
    },
    {
      "name": "users",
      "supported_replication_keys": [],
      "fields": [...]
    }
  ]
}
```

### Validate JQL

```
POST /api/v1/sources/{id}/jira/validate-jql
Content-Type: application/json

{
  "jql": "project = PROJ1 AND updated > -30d"
}

Response 200:
{
  "valid": true,
  "estimated_count": 150
}

Response 400:
{
  "valid": false,
  "error": "Field 'invalid_field' does not exist"
}
```

### Preview Jira Data

```
POST /api/v1/sources/{id}/jira/preview
Content-Type: application/json

{
  "projects": ["PROJ1"],
  "streams": ["issues"],
  "jql_filters": {"issues": "updated > -7d"},
  "batch_size": 50
}

Response 200:
{
  "preview_id": "uuid",
  "streams": {
    "issues": {
      "record_count": 42,
      "schema": [...],
      "sample_records": [...]
    }
  }
}

Response 400:
{
  "error": {
    "type": "auth",
    "message": "Authentication failed. Check your API token.",
    "suggestion": "Generate a new API token in Jira settings."
  }
}
```

---

## Error Classification

| Type | HTTP Codes | Example | User Message |
|------|-----------|---------|--------------|
| auth | 401, 403 | Invalid token | "Ошибка авторизации. Проверьте email и API token." |
| network | timeout, connection refused | Jira unreachable | "Ошибка сети. Проверьте URL и доступность Jira." |
| config | 400, validation | Invalid JQL | "Ошибка конфигурации: {detail}" |
| runtime | 429, 5xx | Rate limit, server error | "Временная ошибка Jira. Попробуйте позже." |

---

## Testing Plan

### Unit Tests

- Validation of Jira URL format
- JQL syntax validation
- Config serialization/deserialization
- Error classification logic
- Credential masking

### Integration Tests

- Create Jira source → verify DB record
- Update credentials → verify encryption
- Preview flow with mock Jira API
- Meltano tap-jira execution with test config
- State persistence for incremental loads

### E2E Tests (UI)

- Full happy path: create source → configure → preview → create flow
- Error handling: invalid credentials → show auth error
- Error handling: network timeout → show network error
- Draft saving and restoration
- Flow execution with scheduled run

---

## Rollout / Migration Notes

### Database Changes

- No schema migration required (reusing existing source model)
- `source_type` enum/values extended with 'jira'
- Optional: add `extraction_config` JSON field to sources or flows

### Feature Flags

- Consider feature flag `jira_connector_enabled` for controlled rollout

### Meltano Setup

- Install `tap-jira` plugin: `meltano add extractor tap-jira`
- Configure tap in meltano.yml template

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Пользователь создаёт Jira source за ≤ 3 минуты в 90% случаев.
- **SC-002**: 95% корректных credentials проходят валидацию с первого раза.
- **SC-003**: Preview показывает результаты за ≤ 30 секунд для типичного набора данных (до 100 records).
- **SC-004**: 100% ошибок классифицированы и показаны с информативным сообщением.
- **SC-005**: Поток успешно загружает данные из Jira в целевую БД.
- **SC-006**: Инкрементальная загрузка корректно использует state между запусками.
- **SC-007**: Существующие postgres и s3 коннекторы работают без регрессий.

---

## Assumptions

- Jira Cloud API используется (Atlassian Cloud). Jira Server/DC может требовать адаптации.
- API token — основной метод аутентификации. OAuth2 может быть добавлен позже.
- tap-jira Meltano extractor поддерживает необходимые streams и replication keys.
- Максимальный объём данных для preview — 100 records (в соответствии с существующим паттерном).
