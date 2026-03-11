# Code Review #2 — gen_dwh

**Дата:** 2026-03-10
**Ветка:** `003-jira-connector`
**Всего найдено:** ~85 проблем (Backend: 31, Frontend: 42, Infra: 12)

---

## Содержание

- [1. Критические баги](#1-критические-баги)
- [2. Legacy и неиспользуемый код](#2-legacy-и-неиспользуемый-код)
- [3. Дублирование кода](#3-дублирование-кода)
- [4. Архитектурные проблемы](#4-архитектурные-проблемы)
- [5. Инфраструктура и безопасность](#5-инфраструктура-и-безопасность)
- [6. Миграции и БД](#6-миграции-и-бд)
- [7. Тесты](#7-тесты)
- [8. План устранения](#8-план-устранения)

---

## 1. Критические баги

### CRIT-1: `await` на синхронном `session.delete()`

| | |
|---|---|
| **Файл** | `backend/src/services/schedule_service.py:88` |
| **Severity** | CRITICAL |
| **Влияние** | `TypeError` в рантайме при удалении расписания |

```python
# Сейчас (ошибка):
await self.session.delete(schedule)

# Исправление:
self.session.delete(schedule)
```

SQLAlchemy `session.delete()` — синхронный метод. `await` вызовет `TypeError: object NoneType can't be used in 'await' expression`.

---

### CRIT-2: SQL Injection через LIKE-wildcards в AuditService

| | |
|---|---|
| **Файл** | `backend/src/services/audit_service.py:35,37` |
| **Severity** | CRITICAL |
| **Влияние** | Обход фильтрации аудит-логов, утечка данных |

```python
# Сейчас (уязвимо):
query = query.where(func.lower(AuditEvent.user_email).like(f"%{user_email.strip().lower()}%"))

# Исправление:
escaped = user_email.strip().lower().replace("%", "\\%").replace("_", "\\_")
query = query.where(func.lower(AuditEvent.user_email).like(f"%{escaped}%", escape="\\"))
```

Пользовательский ввод `%` или `_` не экранируется — позволяет видеть чужие аудит-логи.

---

### CRIT-3: Нарушение транзакционности в NotificationService

| | |
|---|---|
| **Файл** | `backend/src/services/notification_service.py:36-37,65,77` |
| **Severity** | CRITICAL |
| **Влияние** | Невозможно откатить уведомление при сбое транзакции |

```python
# Сейчас — всегда коммитит:
await self.session.commit()

# Исправление — добавить параметр auto_commit как в остальных сервисах:
async def create_notification(self, ..., auto_commit: bool = True) -> Notification:
    ...
    if auto_commit:
        await self.session.commit()
```

Аналогично для `mark_read()` и `mark_all_read()`.

---

### CRIT-4: Потенциальный NULL user_id при создании WorkspaceMembership

| | |
|---|---|
| **Файл** | `backend/src/core/workspace_auth.py:227-232` |
| **Severity** | CRITICAL |
| **Влияние** | NOT NULL constraint violation |

```python
# Проблемный участок:
membership = WorkspaceMembership(
    user_id=user.id,  # user.id может быть None если flush не завершился
    tenant_id=workspace.id,
    role=role,
)
```

**Исправление:** Добавить явную проверку `assert user.id is not None` после flush, или обернуть в `try/except`.

---

## 2. Legacy и неиспользуемый код

### LEGACY-1: Удалённый файл `backend/src/core/auth.py`

| | |
|---|---|
| **Статус в git** | `D` (deleted) |
| **Действие** | Проверить, что нигде не импортируется; удалить все ссылки |

---

### LEGACY-2: Вся директория `frontend/src/components/FlowWizard/` (~420 строк)

| | |
|---|---|
| **Файлы** | `FlowWizard.tsx`, `SourceStep.tsx`, `TableSelectionStep.tsx`, `TableConfigStep.tsx`, `TargetConfigStep.tsx`, `ScheduleStep.tsx` |
| **Действие** | Ни один компонент не импортируется. Удалить или интегрировать в `FlowCreate` |

---

### LEGACY-3: Удалённый `frontend/src/components/common/LoadingStates.tsx`

| | |
|---|---|
| **Статус в git** | `D` (deleted) |
| **Действие** | Проверить импорты, заменить на актуальные компоненты |

---

### LEGACY-4: Неиспользуемые поля моделей

| Файл | Поле | Проблема |
|---|---|---|
| `backend/src/models/run.py:48` | `error_details` (JSONB) | Нигде не заполняется |
| `backend/src/models/run.py:52` | `meltano_state_file` | Использование неясно |

**Действие:** Проверить реальное использование; если не нужны — удалить поля + миграцию.

---

### LEGACY-5: Дублированный локальный тип `JiraStreamConfig`

| | |
|---|---|
| **Файл** | `frontend/src/pages/Flows/FlowCreate.tsx:26-30` |
| **Дубликат** | `JiraExtractionConfig` в `frontend/src/services/jiraApi.ts` |
| **Действие** | Заменить на импорт из `jiraApi.ts` |

---

### LEGACY-6: Неиспользуемый импорт в JiraStreamSelector

| | |
|---|---|
| **Файл** | `frontend/src/components/JiraConfig/JiraStreamSelector.tsx:1` |
| **Действие** | Удалить неиспользуемый импорт |

---

## 3. Дублирование кода

### DUP-1: Regex валидации PostgreSQL-идентификаторов (3 файла)

| Файл | Строка |
|---|---|
| `backend/src/services/flow_service.py` | 20 |
| `backend/src/services/preview.py` | 27 |
| `backend/src/services/scheduler.py` | 50 |

```python
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
```

**Исправление:** Создать `backend/src/core/identifiers.py`:

```python
import re

POSTGRESQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

def validate_identifier(value: str, field: str = "identifier") -> str:
    if not POSTGRESQL_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid {field}")
    return value
```

---

### DUP-2: Нормализация имён таблиц (2 файла)

| Файл | Строки |
|---|---|
| `backend/src/services/flow_service.py` | 206-257 |
| `backend/src/services/scheduler.py` | 68-82 |

Почти идентичные `_normalize_table_identifier()` и `_default_target_table_name()`.

**Исправление:** Вынести в `backend/src/core/identifiers.py`.

---

### DUP-3: Нормализация Jira auth type (2 подхода)

| Файл | Строки |
|---|---|
| `backend/src/services/source_service.py` | 32-50 |
| `backend/src/api/v1/jira.py` | 48-51 |

**Исправление:** Единая функция в `source_service.py` или отдельный модуль.

---

### DUP-4: Проверка `actor_id` (4 повтора)

| | |
|---|---|
| **Файл** | `backend/src/api/v1/notifications.py:39,54,68,82` |

```python
if not actor_id:
    raise HTTPException(status_code=403, detail="...")
```

**Исправление:** Создать dependency `require_actor_id()`.

---

### DUP-5: Извлечение workspace roles (2 файла)

| Файл | Строки |
|---|---|
| `backend/src/core/workspace_auth.py` | 70-81 |
| `backend/src/api/v1/auth.py` | 183-196 |

**Исправление:** Единый `extract_workspace_roles()` в `workspace_auth.py`.

---

### DUP-6: Frontend — паттерн fetch + pagination (4 страницы)

| Файл | Проблема |
|---|---|
| `frontend/src/pages/Sources/SourcesList.tsx` | Ручной `useState` + `useEffect` + fetch + pagination |
| `frontend/src/pages/Flows/FlowsList.tsx` | То же самое |
| `frontend/src/pages/Runs/RunsList.tsx` | То же самое |
| `frontend/src/pages/Audit/AuditLog.tsx` | То же самое |

**Исправление:** Хук `useListWithPagination.ts` уже создан, но не используется повсеместно. Внедрить его во все страницы-списки.

---

### DUP-7: Frontend — форматирование дат (~10 мест)

`new Date(x).toLocaleString("ru-RU")` повторяется без единой утилиты.

**Исправление:** Создать `frontend/src/utils/formatDate.ts`.

---

### DUP-8: Frontend — Status badges (2 компонента)

| Файл | Проблема |
|---|---|
| `frontend/src/components/RunStatus.tsx` | Маппинг статус → цвет |
| `frontend/src/components/RunProgressBar.tsx` | Дублированный маппинг |

**Исправление:** Единый маппинг в `constants/statusColors.ts`.

---

### DUP-9: Frontend — обработка ошибок API (50+ мест)

```typescript
onError: (error: unknown) => {
  addToast("error", extractApiErrorMessage(error, "Fallback message"));
}
```

**Исправление:** Создать хук `useErrorToast()` или обёртку для `useMutation`.

---

## 4. Архитектурные проблемы

### ARCH-1: Race condition в `RunService.create_run`

| | |
|---|---|
| **Файл** | `backend/src/services/run_service.py:75-102` |
| **Severity** | HIGH |

Retry-loop (3 попытки) маскирует проблему конкурентности. После `IntegrityError` + `rollback` состояние сессии неопределённо.

**Исправление:** Использовать DB sequence для `run_number` или `SERIALIZABLE` isolation level.

---

### ARCH-2: Путаница в именах auth-функций

| | |
|---|---|
| **Файл** | `backend/src/core/workspace_auth.py:182-297` |

- `sync_auth_context_from_keycloak_payload()` — мутирует БД
- `load_auth_context_from_keycloak_payload()` — только чтение

**Исправление:** Переименовать для ясности:
- `sync_and_build_auth_context()`
- `build_auth_context_readonly()`

---

### ARCH-3: Circular dependency в моделях

| | |
|---|---|
| **Файл** | `backend/src/models/user.py:27` |

`WorkspaceMembership` используется в relationship без `TYPE_CHECKING` guard.

**Исправление:**
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.models.workspace_membership import WorkspaceMembership

memberships: Mapped[list["WorkspaceMembership"]] = relationship(back_populates="user")
```

---

### ARCH-4: Frontend — отсутствие Error Boundaries

Ни один компонент не обёрнут в Error Boundary. Ошибка в одном виджете роняет всю страницу.

**Исправление:** Обернуть ключевые страницы/виджеты в `<ErrorBoundary>`.

---

### ARCH-5: Frontend — утечка памяти в Toast

| | |
|---|---|
| **Файл** | `frontend/src/components/common/Toast.tsx:24-30` |

`setTimeout` без `clearTimeout` при размонтировании компонента.

**Исправление:** Хранить timer ref и очищать в cleanup.

---

### ARCH-6: Frontend — race condition в FlowDetail

| | |
|---|---|
| **Файл** | `frontend/src/pages/Flows/FlowDetail.tsx:99-109` |

Два `useEffect` создают race condition: `sourceSchemas` обновляет `selectedSchema`, от которого зависит запрос `sourceTables`. Оба эффекта могут сработать с задержкой.

**Исправление:** Объединить в один эффект или использовать `useMemo` для derived state.

---

### ARCH-7: Frontend — нет отмены запросов при размонтировании

API-запросы продолжают выполняться после смены страницы, вызывая `setState` на unmounted компонентах.

**Исправление:** Использовать `AbortController` или полагаться на `react-query` (который это делает автоматически для queries, но не для mutations).

---

### ARCH-8: Backend — import внутри функций

| Файл | Строка | Импорт |
|---|---|---|
| `backend/src/services/notification_service.py` | 80 | `from sqlalchemy import func` |
| `backend/src/services/schedule_service.py` | 73 | `from datetime import timedelta` |

**Исправление:** Вынести импорты на уровень модуля.

---

### ARCH-9: Backend — HTTPException с dict вместо string в detail

| | |
|---|---|
| **Файл** | `backend/src/api/v1/jira.py:156-165` |

```python
raise HTTPException(status_code=400, detail={"message": ..., "error_type": ...})
```

FastAPI ожидает строку в `detail` по умолчанию. Dict может некорректно сериализоваться.

**Исправление:** Использовать string для `detail` или явно настроить exception handler.

---

### ARCH-10: Backend — двойной rollback

| | |
|---|---|
| **Файл** | `backend/src/api/v1/flows.py:168-173, 246-256, 293-297` |

```python
except ValueError as exc:
    await db.rollback()
    raise HTTPException(...)
except Exception:
    await db.rollback()
    raise
```

Если первый `rollback()` упадёт, exception handling потеряется.

**Исправление:** Использовать единый `except` или context manager для транзакций.

---

## 5. Инфраструктура и безопасность

### INFRA-1: Frontend-контейнер без healthcheck

| | |
|---|---|
| **Файл** | `docker/docker-compose.yml:237-248` |

**Исправление:** Добавить:
```yaml
healthcheck:
  test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/index.html"]
  interval: 10s
  timeout: 5s
  retries: 3
```

---

### INFRA-2: Frontend Dockerfile — pnpm fallback скрывает ошибки

| | |
|---|---|
| **Файл** | `frontend/Dockerfile:6` |

```dockerfile
RUN corepack enable && pnpm install --frozen-lockfile 2>/dev/null || npm install
```

**Исправление:** Убрать `2>/dev/null` и fallback. Определиться: или pnpm, или npm.

---

### INFRA-3: Backend Dockerfile — `pip` вместо `uv`

| | |
|---|---|
| **Файл** | `backend/Dockerfile` |

В проекте есть `uv.lock`, но Dockerfile использует `pip install`.

**Исправление:** Перейти на `uv pip install` или `uv sync`.

---

### INFRA-4: Keycloak в dev-режиме

| | |
|---|---|
| **Файл** | `docker/docker-compose.yml:87` |

```yaml
command: start-dev
```

**Исправление:** Использовать `start` для production; параметризовать через env var.

---

### INFRA-5: Celery worker/beat без healthcheck

| | |
|---|---|
| **Файл** | `docker/docker-compose.yml:189-235` |

**Исправление:** Добавить healthcheck через `celery inspect ping`.

---

### INFRA-6: Redis healthcheck выставляет пароль

| | |
|---|---|
| **Файл** | `docker/docker-compose.yml:76` |

```yaml
test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
```

**Исправление:** Использовать `REDISCLI_AUTH` env var вместо `-a` флага.

---

### INFRA-7: `AUTH_COOKIE_SECURE` по умолчанию `false`

| | |
|---|---|
| **Файл** | `docker/.env.example:38` |

**Исправление:** Установить `true` по умолчанию; явно выставлять `false` только для dev.

---

### INFRA-8: Конфликт дефолтов `KC_SSL_REQUIRED`

| Файл | Значение |
|---|---|
| `docker/.env.example:15` | `none` |
| `docker/keycloak-init.sh:10` | `external` |

**Исправление:** Согласовать — использовать `external` везде.

---

### INFRA-9: `directAccessGrantsEnabled=true` в Keycloak

| | |
|---|---|
| **Файл** | `docker/keycloak-init.sh:54` |

Resource Owner Password Credentials flow — deprecated OAuth flow.

**Исправление:** Установить `false`, если не используется.

---

### INFRA-10: tap-jira через GitHub tarball вместо PyPI

| | |
|---|---|
| **Файл** | `meltano/meltano.yml:34-36` |

**Риск:** Supply chain — если тег удалят, билд сломается. Нет верификации.

**Исправление:** Опубликовать на PyPI или зафиксировать commit hash.

---

## 6. Миграции и БД

### MIG-1: Миграции 010-014 без downgrade

| | |
|---|---|
| **Файлы** | `backend/migrations/versions/010-014` |
| **Проблема** | Пустые `downgrade()` — невозможно откатить |

---

### MIG-2: Отсутствуют индексы на FK

| Таблица | Колонка | Миграция |
|---|---|---|
| `flow_tables` | `source_id` | 003 |
| `source_credentials` | `source_id` | 002 |
| `workspace_memberships` | FK колонки | 012 |

---

### MIG-3: Нет partial indexes для soft-delete

Запросы `WHERE deleted_at IS NULL` не оптимизированы.

**Исправление:** Создать partial index:
```sql
CREATE INDEX idx_flows_active ON flows(id) WHERE deleted_at IS NULL;
```

---

### MIG-4: Нет составных индексов для частых запросов

| Индекс | Таблица |
|---|---|
| `(status, deleted_at)` | `flows` |
| `(flow_id, status)` | `runs` |
| `(is_active, next_run_at)` | `schedules` |
| `(user_id, is_read, created_at)` | `notifications` |

---

### MIG-5: Migration 010 — downgrade не обрабатывает NULL в source_id

| | |
|---|---|
| **Файл** | `backend/migrations/versions/010_run_cancel_and_source_deletion_guards.py:54-61` |

Downgrade воссоздаёт NOT NULL constraint, но данные могут уже содержать NULL.

---

## 7. Тесты

### TEST-1: Нет тестов для race condition в RunService

Критический путь `create_run` с конкурентными запросами не покрыт.

---

### TEST-2: Нет тестов для transaction rollback сценариев

Все update/delete операции должны тестировать откат.

---

### TEST-3: `SimpleNamespace` вместо реальных моделей в моках

| | |
|---|---|
| **Файл** | `backend/tests/unit/test_source_service.py:65-132` |

Не проверяет реальные ограничения моделей.

---

### TEST-4: Нет E2E тестов для миграций

Нет проверки, что все миграции применяются чисто и цикл upgrade/downgrade работает.

---

### TEST-5: Тестовое окружение не соответствует production

In-memory app без реальной БД. Production-баги не ловятся.

---

### TEST-6: `test_meltano_metrics.py` может быть устаревшим

Тестирует old API, требует проверки актуальности.

---

## 8. План устранения

### Фаза 1: Критическое (1-2 дня)

| # | Задача | Файлы | Приоритет |
|---|---|---|---|
| 1 | Убрать `await` с `session.delete()` | `schedule_service.py` | CRITICAL |
| 2 | Экранировать SQL wildcards в LIKE | `audit_service.py` | CRITICAL |
| 3 | Добавить `auto_commit` в NotificationService | `notification_service.py` | CRITICAL |
| 4 | Проверить flush перед `user.id` | `workspace_auth.py` | CRITICAL |
| 5 | `AUTH_COOKIE_SECURE=true` по умолчанию | `.env.example` | HIGH |
| 6 | Согласовать `KC_SSL_REQUIRED` | `.env.example`, `keycloak-init.sh` | HIGH |

### Фаза 2: Рефакторинг backend (3-5 дней)

| # | Задача | Файлы |
|---|---|---|
| 7 | Создать `core/identifiers.py` — единый модуль для regex, нормализации, валидации | Новый файл + `flow_service.py`, `preview.py`, `scheduler.py` |
| 8 | Исправить race condition в RunService | `run_service.py` |
| 9 | Добавить dependency `require_actor_id()` | `notifications.py`, `deps.py` |
| 10 | Fix circular import в `user.py` | `user.py` |
| 11 | Вынести импорты из функций на уровень модуля | `notification_service.py`, `schedule_service.py` |
| 12 | Переименовать auth context функции | `workspace_auth.py` |
| 13 | Единая нормализация jira auth type | `source_service.py`, `jira.py` |
| 14 | Исправить HTTPException detail dict → string | `jira.py` |

### Фаза 3: Рефакторинг frontend (3-5 дней)

| # | Задача | Файлы |
|---|---|---|
| 15 | Удалить `components/FlowWizard/` или интегрировать | 6 файлов |
| 16 | Внедрить `useListWithPagination` повсеместно | 4 страницы-списка |
| 17 | Создать `utils/formatDate.ts` | Новый файл + ~10 мест |
| 18 | Единый маппинг статусов | `RunStatus.tsx`, `RunProgressBar.tsx` |
| 19 | Создать хук `useErrorToast()` | Новый хук + ~50 мест |
| 20 | Добавить Error Boundaries | Обёртки для ключевых страниц |
| 21 | Исправить утечку памяти в Toast | `Toast.tsx` |
| 22 | Исправить race condition в FlowDetail | `FlowDetail.tsx` |
| 23 | Удалить дублированный тип `JiraStreamConfig` | `FlowCreate.tsx` |
| 24 | Устранить неиспользуемый импорт | `JiraStreamSelector.tsx` |

### Фаза 4: Инфраструктура (2-3 дня)

| # | Задача | Файлы |
|---|---|---|
| 25 | Healthcheck для frontend-контейнера | `docker-compose.yml` |
| 26 | Healthcheck для Celery worker/beat | `docker-compose.yml` |
| 27 | Убрать pnpm fallback, определиться с package manager | `frontend/Dockerfile` |
| 28 | Перейти на `uv` в backend Dockerfile | `backend/Dockerfile` |
| 29 | Параметризовать Keycloak dev/prod режим | `docker-compose.yml` |
| 30 | Скрыть Redis пароль в healthcheck | `docker-compose.yml` |
| 31 | Отключить `directAccessGrantsEnabled` | `keycloak-init.sh` |
| 32 | Зафиксировать tap-jira по commit hash | `meltano/meltano.yml` |

### Фаза 5: Миграции и БД (1-2 дня)

| # | Задача | Файлы |
|---|---|---|
| 33 | Новая миграция: индексы на FK | Новый файл |
| 34 | Partial indexes для soft-delete | Новый файл |
| 35 | Составные индексы для частых запросов | Новый файл |
| 36 | Downgrade для миграций 010-014 | Существующие файлы |
| 37 | Fix downgrade в migration 010 (NULL handling) | `010_run_cancel_...py` |

### Фаза 6: Тесты (3-5 дней)

| # | Задача |
|---|---|
| 38 | Тесты на race condition в `RunService.create_run` |
| 39 | Тесты на transaction rollback для всех CUD операций |
| 40 | E2E тесты для миграций (upgrade/downgrade cycle) |
| 41 | Заменить `SimpleNamespace` на реальные модели/Mock(spec=...) |
| 42 | Проверить актуальность `test_meltano_metrics.py` |

---

## Сводка по приоритетам

| Приоритет | Количество | Оценка времени |
|---|---|---|
| CRITICAL (Фаза 1) | 6 задач | 1-2 дня |
| HIGH — Backend (Фаза 2) | 8 задач | 3-5 дней |
| HIGH — Frontend (Фаза 3) | 10 задач | 3-5 дней |
| MEDIUM — Infra (Фаза 4) | 8 задач | 2-3 дня |
| MEDIUM — Миграции (Фаза 5) | 5 задач | 1-2 дня |
| LOW — Тесты (Фаза 6) | 5 задач | 3-5 дней |
| **ИТОГО** | **42 задачи** | **~13-22 дня** |
