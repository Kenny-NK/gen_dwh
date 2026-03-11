# Отчёт по ревью кода проекта GenDWH

**Дата:** 2026-03-11
**Модель:** GLM-4.5
**Ветка:** 003-jira-connector

---

# Итоговая оценка: 7.5/10

## Детализация по компонентам

| Компонент | Оценка | Вес |
|-----------|--------|-----|
| Backend (Python/FastAPI) | 8/10 | 35% |
| Frontend (React/TypeScript) | 7/10 | 30% |
| DevOps / Infrastructure | 8/10 | 20% |
| Тестирование | 6/10 | 10% |
| Документация | 5/10 | 5% |

---

## Краткое обоснование

**Плюсы (+)**
- Современный стек (FastAPI, SQLAlchemy 2.0 async, React 18, TypeScript)
- Правильная мультитенантная архитектура
- RBAC и security best practices
- Docker Compose с healthchecks и resource limits
- Prometheus metrics

**Минусы (−)**
- Нет CI/CD pipeline
- Клиентская фильтрация вместо серверной
- Нет E2E тестов, слабые mocks в unit тестах
- Отсутствует документация (README, architecture diagrams)
- Дублирование кода в error handling

---

## Для достижения 9/10 необходимо

1. CI/CD с автотестами
2. Server-side пагинация и фильтрация
3. Integration тесты с testcontainers
4. README с quickstart
5. Централизованный error handling middleware

**Вердикт**: Код production-ready для MVP, требует доработки для enterprise-использования.

---

## 1. Backend (Python/FastAPI) — Оценка: 8/10

### Сильные стороны

**Архитектура и структура**
- Чёткое разделение слоёв: `api/`, `services/`, `models/`, `core/`, `middleware/`
- Dependency Injection через FastAPI Depends (`src/api/deps.py:24-53`)
- Мультитенантность с изолированными схемами БД (tenant schema pattern)

**Качество кода**
- Асинхронный код на SQLAlchemy 2.0 с `AsyncSession`
- Typed Python с type hints
- Pydantic для валидации и настроек (`src/core/config.py:9-114`)

```python
# Пример хорошего кода - сервис с транзакциями
async def create_flow(..., auto_commit: bool = True) -> Run:
    for _ in range(3):  # Retry для race condition
        flow_lock = await self.session.execute(
            select(Flow.id).where(...).with_for_update()
        )
        ...
        try:
            await self.session.flush()
            if auto_commit:
                await self.session.commit()
            return run
        except IntegrityError:
            await self.session.rollback()
```

**Безопасность**
- Валидация секретов в production (`src/core/config.py:76-101`)
- RBAC с permissions (`src/core/permissions.py`)
- Защита от SQL injection через SQLAlchemy ORM
- Rate limiting middleware

**Обработка ошибок**
- Централизованная классификация ошибок Jira (`src/services/jira_service.py:180-245`)
- Graceful degradation при недоступности Keycloak

### Проблемы и рекомендации

**1. Дублирование кода в API endpoints**

`src/api/v1/flows.py` содержит повторяющийся паттерн:
```python
try:
    # operation
    await db.commit()
except HTTPException:
    raise
except Exception:
    await db.rollback()
    raise
```
**Рекомендация**: Вынести в декоратор или middleware для автоматического rollback.

**2. Hardcoded сообщения на русском**

```python
# src/api/deps.py:33
detail="Активный workspace не выбран"
```
**Рекомендация**: Использовать i18n или вынести в константы.

**3. Отсутствие пагинации на уровне БД**

`src/services/run_service.py:30-44`:
```python
async def list_runs(..., limit: int = 50, offset: int = 0) -> list[Run]:
    query = select(Run)
    ...
    query = query.order_by(Run.created_at.desc()).limit(limit).offset(offset)
```
Пагинация есть, но `count_runs` выполняется отдельным запросом.

**4. Тесты**

- 27 тестовых файлов — хорошее покрытие ключевых сервисов
- Но используются mock-объекты вместо test fixtures с реальной БД:
```python
# tests/unit/test_run_service.py
class _DummySession:  # Слишком простой mock
    async def execute(self, _query):
        return _DummyResult(self._runs)
```
**Рекомендация**: Добавить integration тесты с test containers.

---

## 2. Frontend (React/TypeScript) — Оценка: 7/10

### Сильные стороны

**Типизация**
- TypeScript с proper interfaces
- Generic components (`src/components/common/Table.tsx:17`):
```typescript
interface TableProps<T extends TableRow> {
  columns: Column<T>[];
  data: T[];
  onRowClick?: (item: T) => void;
}
```

**State Management**
- React Query для server state (`@tanstack/react-query`)
- Custom hooks для инкапсуляции логики (`useAuth`, `useListWithPagination`)

**UX паттерны**
- Toast notifications для обратной связи
- Modal confirmations для деструктивных действий
- Loading states

### Проблемы и рекомендации

**1. Клиентская фильтрация вместо серверной**

`src/pages/Flows/FlowsList.tsx:106-115`:
```typescript
const filteredFlows = flows.filter((flow) => {
  if (!normalizedSearch) return true;
  return (
    flow.name.toLowerCase().includes(normalizedSearch) ||
    ...
  );
});
```
**Проблема**: Фильтрация происходит на клиенте после загрузки всех данных.
**Рекомендация**: Добавить search параметр в API запрос.

**2. Дублирование API error handling**

```typescript
// В каждом компоненте
const { showErrorToast } = useErrorToast();
onError: (error: unknown) => {
  showErrorToast(error, "Не удалось удалить поток");
},
```
**Рекомендация**: Вынести в axios interceptor с централизованной обработкой.

**3. Отсутствие memoization**

`FlowsList.tsx:67-104` — columns array создаётся на каждом рендере.
**Рекомендация**: Вынести в `useMemo` или outside component.

**4. Слабая типизация API responses**

```typescript
interface Flow {
  [key: string]: unknown;  // Слишком broadly typed
}
```

**5. Accessibility**
- Table component поддерживает keyboard navigation — хорошо
- Отсутствуют ARIA labels на некоторых интерактивных элементах

---

## 3. DevOps и Архитектура — Оценка: 8/10

### Сильные стороны

**Docker Compose**
- Правильное использование healthchecks
- Зависимости между сервисами с conditions
- Resource limits (mem_limit, cpus)
- Разделение system и business БД

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U gendwh -d gendwh_system"]
  interval: 5s
  timeout: 5s
  retries: 5
```

**Конфигурация**
- Environment-based configuration
- Валидация настроек в Pydantic
- Разделение dev/prod через `enforce_secure_secrets`

**Observability**
- Prometheus metrics endpoint
- Structured logging

### Проблемы и рекомендации

**1. Отсутствие CI/CD**

Нет файлов `.github/workflows` или аналогов.

**Рекомендация**: Добавить pipeline с:
- Lint (ruff, eslint)
- Type check (mypy, tsc)
- Tests
- Docker build

**2. Secrets management**

```yaml
POSTGRES_PASSWORD: ${POSTGRES_SYSTEM_PASSWORD}
```
Secrets передаются через env, что приемлемо для dev, но не для production.

**Рекомендация**: Docker secrets или HashiCorp Vault.

**3. Отсутствие rate limiting per tenant**

Rate limit общий на весь сервис, а не per workspace.

**4. Keycloak в dev mode**

```yaml
command: start-dev
```
Для production нужен `start` с proper TLS.

**5. Дополнительные находки**
- Отсутствие `.dockerignore` — потенциальная проблема безопасности build context
- Нет сетевой сегментации между сервисами
- Отсутствие централизованного логирования (ELK/Loki)
- Нет Grafana для визуализации метрик

---

## 4. Тестовое покрытие — Оценка: 6/10

### Покрытие по модулям

| Модуль | Unit | Integration |
|--------|------|-------------|
| Config | ✅ | - |
| RunService | ✅ | - |
| JiraService | ✅ | - |
| FlowService | ✅ | - |
| Auth | - | ✅ |
| API endpoints | - | ✅ (частично) |

### Проблемы

1. **Отсутствуют E2E тесты** для критических flows (создание flow, запуск extraction)
2. **Минимальные assertions** в некоторых тестах
3. **Нет coverage reporting** (pytest-cov)

---

## 5. Безопасность — Оценка: 7.5/10

### Сильные стороны
- OIDC/OAuth2 через Keycloak
- Tenant isolation на уровне схемы БД
- RBAC с granular permissions
- Валидация входных данных через Pydantic
- Защита от secrets в production config

### Риски
1. **CORS**: `cors_allowed_origins` строка, не массив
2. **Отсутствие CSP headers**
3. **Нет audit trail** для всех операций (только частично через `log_audit_event`)

---

## 6. Документация — Оценка: 5/10

### Проблемы
- Отсутствует README с quickstart
- Нет архитектурных диаграмм
- Нет API documentation examples
- Отсутствует CONTRIBUTING.md

---

## Итоговые рекомендации

### Приоритет 1 (Критично)
1. Добавить CI/CD pipeline
2. Перенести фильтрацию на backend
3. Добавить integration тесты с testcontainers

### Приоритет 2 (Важно)
1. Вынести duplicate error handling в middleware
2. Добавить memoization в React компоненты
3. Настроить coverage reporting

### Приоритет 3 (Улучшения)
1. Добавить OpenAPI schema examples
2. Улучшить TypeScript типы (убрать `unknown`)
3. Добавить ARIA labels для accessibility
4. Документировать API с примерами
5. Добавить README с инструкциями по запуску

---

## Метрики проекта

| Метрика | Значение |
|---------|----------|
| Backend Python файлов | ~80 |
| Frontend TS/TSX файлов | ~60 |
| Тестовых файлов | 27 |
| Средний размер файла | ~150 LOC |
| Количество endpoints | ~30 |
| Docker services | 10 |
