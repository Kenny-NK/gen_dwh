# Code Review: gen_dwh

**Дата:** 2026-03-10
**Ветка:** 003-jira-connector
**Ревьюер:** Claude Code

---

## ГРУППА 1: Исправление багов

**Приоритет: немедленно**

### 1.1. Дублированный ключ `"viewer"` в KEYCLOAK_ROLE_PERMISSIONS

- **Файл:** `backend/src/core/permissions.py:63-64`
- **Суть:** Ключ `"viewer"` определён дважды — строка 63 (`ROLE_PERMISSIONS["viewer"]`) молча перезаписывается строкой 64 (явный набор). Оба значения сейчас идентичны (`SOURCES_READ`, `FLOWS_READ`, `PREVIEW_READ`, `SCHEDULES_READ`), но это бомба замедленного действия — при изменении `ROLE_PERMISSIONS["viewer"]` вторая запись не обновится.
- **Действие:** Удалить строку 63 (дублирующую ссылку), оставить явное определение на строках 64-69.

### 1.2. Неверный return type в `mask_value()`

- **Файл:** `backend/src/services/masking.py:48-51`
- **Суть:** Сигнатура `-> str`, но при `value is None` возвращает `None`. Mypy/pyright поймают как ошибку, вызывающий код может получить `AttributeError`.
- **Действие:** Изменить тип возврата на `str | None`.

### 1.3. Race condition в `_run_in_worker_loop()`

- **Файл:** `backend/src/services/scheduler.py:55-60`
- **Суть:** Глобальный `_worker_loop` мутируется без блокировки. При параллельных вызовах из разных потоков Celery возможно создание двух event loop'ов.
- **Действие:** Добавить `threading.Lock` вокруг инициализации, либо заменить на `asyncio.run()`.

---

## ГРУППА 2: Удаление dead code

**Приоритет: высокий (уменьшает путаницу и объём кодовой базы)**

### 2.1. Backend — неиспользуемые классы и функции

| # | Что удалить | Файл : строки | Подтверждение |
|---|---|---|---|
| A | Класс `KeycloakClient` + синглтон `keycloak_client` | `backend/src/core/auth.py:9-37` | Grep по `src/` — нигде не импортируется. Вся auth-логика идёт через `security.py:decode_jwt()` |
| B | Функция `permissions_from_keycloak_roles()` | `backend/src/core/permissions.py:91-98` | Grep — единственное вхождение это определение |
| C | Дубль `require_permission()` | `backend/src/core/permissions.py:101-124` | Ноль импортов из `core.permissions`. Все endpoint'ы используют версию из `api/deps.py:60-69` |
| D | Функция `detect_pii_type()` | `backend/src/services/masking.py:22-45` | Grep — единственное вхождение это определение. Нигде не вызывается |

Также удалить ставший ненужным импорт `from typing import Callable` из `permissions.py:4` после удаления `require_permission()`.

### 2.2. Frontend — неиспользуемые компоненты и функции

| # | Что удалить | Файл : строки | Подтверждение |
|---|---|---|---|
| A | `Spinner`, `TableSkeleton`, `CardSkeleton`, `PageLoader` | `frontend/src/components/common/LoadingStates.tsx:7-50` | Grep — ноль импортов. Весь файл можно удалить |
| B | Функция `formatNumberRu` | `frontend/src/utils/numberFormat.ts:19-27` | Grep — нигде не импортируется. `formatCompactNumberRu` используется в 4 файлах (оставить) |

---

## ГРУППА 3: Устранение дублирования кода — Backend

**Приоритет: средний**

### 3.1. Централизация `_quote_ident()`

**Создать:** `backend/src/core/db_utils.py`

```python
def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
```

**Удалить локальные копии и заменить импортом `from src.core.db_utils import quote_ident`:**

| # | Файл | Строка определения |
|---|---|---|
| 1 | `backend/src/core/tenant.py` | 15-16 |
| 2 | `backend/src/services/flow_service.py` | 23-24 |
| 3 | `backend/src/services/preview.py` | 36-37 |
| 4 | `backend/src/services/s3_loader.py` | 37-38 |
| 5 | `backend/src/services/jira_loader.py` | 34-35 |

### 3.2. Централизация `_normalize_identifier()`

**Оставить** каноническую версию в `backend/src/services/record_flattening.py:15-21` (уже public `normalize_identifier`).

**Удалить локальные копии и заменить импортом `from src.services.record_flattening import normalize_identifier`:**

| # | Файл | Строка определения | Имя функции |
|---|---|---|---|
| 1 | `backend/src/services/s3_loader.py` | 41-47 | `_normalize_identifier` |
| 2 | `backend/src/services/jira_loader.py` | 38-44 | `_normalize_identifier` |
| 3 | `backend/src/services/scheduler.py` | 63-71 | `_normalize_table_identifier` |

> **Примечание:** В `scheduler.py` функция использует fallback `"table"` и префикс `t_` вместо `c_`. Нужно либо параметризовать каноническую версию (добавить аргумент `digit_prefix="c_"`), либо оставить обёртку-алиас.

### 3.3. Placeholder `"unused-token"` в JiraService

- **Файл:** `backend/src/services/source_service.py:543`
- **Суть:** `JiraService(source.host, source.username, "unused-token", auth_type=auth_type)` — токен передаётся, но `resolve_stream_dependencies()` не делает HTTP-запросов.
- **Действие:** Сделать параметр `token` опциональным в `JiraService.__init__()` (default `None`), передавать `None` вместо строки-заглушки.

---

## ГРУППА 4: Устранение дублирования кода — Frontend

**Приоритет: средний**

### 4.1. Вынести общие label-словари в `frontend/src/constants/labels.ts`

**triggerLabels** — определён 3 раза (с разной капитализацией!):

| # | Файл | Строки | Капитализация |
|---|---|---|---|
| 1 | `frontend/src/pages/Runs/RunsList.tsx` | 29-33 | `"Вручную"` |
| 2 | `frontend/src/pages/Dashboard/RunsWidget.tsx` | 11-15 | `"вручную"` (lowercase!) |
| 3 | `frontend/src/pages/Runs/RunDetail.tsx` | 33-37 | `"Вручную"` |

**writeModeLabels** — определён 2 раза:

| # | Файл | Строки |
|---|---|---|
| 1 | `frontend/src/pages/Flows/FlowsList.tsx` | 26-30 |
| 2 | `frontend/src/pages/Flows/FlowDetail.tsx` | 52-56 |

**Действие:** Создать `frontend/src/constants/labels.ts`, определить один раз, импортировать в 5 файлах. Выбрать единую капитализацию.

### 4.2. Создать утилиту нормализации API-ответов

Паттерн `Array.isArray(payload) ? payload : payload?.items ?? []` повторяется в 6+ файлах:

| # | Файл | Контекст |
|---|---|---|
| 1 | `frontend/src/pages/Dashboard/FlowsWidget.tsx` | ~строка 17-23 |
| 2 | `frontend/src/pages/Dashboard/RunsWidget.tsx` | ~строка 22-29 |
| 3 | `frontend/src/pages/Dashboard/SourcesWidget.tsx` | API вызовы |
| 4 | `frontend/src/pages/Flows/FlowsList.tsx` | ~строка 42-54 |
| 5 | `frontend/src/pages/Flows/FlowDetail.tsx` | ~строка 80-87 |
| 6 | `frontend/src/pages/Runs/RunsList.tsx` | ~строка 50-54 |

**Действие:** Добавить в `frontend/src/services/api.ts`:

```typescript
export function extractItems<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data;
  const obj = data as Record<string, unknown>;
  return Array.isArray(obj?.items) ? (obj.items as T[]) : [];
}
```

Заменить все 6+ вхождений.

### 4.3. Создать хук `useListWithPagination`

Паттерн `useState(page)` + `useState(search)` + `useQuery` с `limit/offset` повторяется в 3 страницах-списках:

| # | Файл | Строки |
|---|---|---|
| 1 | `frontend/src/pages/Sources/SourcesList.tsx` | ~34-36 |
| 2 | `frontend/src/pages/Flows/FlowsList.tsx` | ~36-40 |
| 3 | `frontend/src/pages/Runs/RunsList.tsx` | ~38-40 |

**Действие:** Создать `frontend/src/hooks/useListWithPagination.ts` — generic хук с параметрами `queryKey`, `endpoint`, `pageSize`.

---

## ГРУППА 5: Исправления frontend — типобезопасность и надёжность

**Приоритет: средний**

### 5.1. Нестабильные React-ключи в Table

- **Файл:** `frontend/src/components/common/Table.tsx:49`
- **Суть:** `key={String(item.id ?? i)}` — fallback на array index ломает reconciliation при сортировке/фильтрации.
- **Действие:** Типизировать `data` чтобы `id` было обязательным, или использовать стабильный fallback (например, `crypto.randomUUID()` при маунте для строк без id).

### 5.2. `JSON.stringify()` без защиты от circular references

- **Файл:** `frontend/src/components/JiraConfig/JiraPreviewResults.tsx:78`
- **Суть:** `JSON.stringify(row[key])` может упасть на circular reference.
- **Действие:** Обернуть в `try/catch`, при ошибке возвращать `"[Object]"`.

### 5.3. Hardcoded dummy UUID для валидации cron

- **Файл:** `frontend/src/components/ScheduleBuilder.tsx:30`
- **Суть:** `api.post("/flows/00000000-0000-0000-0000-000000000000/schedule/validate", ...)` — фиктивный UUID.
- **Действие:** Либо создать отдельный backend endpoint `POST /schedules/validate` без привязки к flow, либо пробрасывать реальный `flowId` через props.

### 5.4. Смешение `fetch()` и `axios`

| # | Файл | Строки | Вызов |
|---|---|---|---|
| 1 | `frontend/src/hooks/useAuth.ts` | 32 | `fetch("/api/v1/auth/session", { method: "DELETE" })` |
| 2 | `frontend/src/hooks/useAuth.ts` | 52 | `fetch("/api/v1/auth/me", { credentials: "include" })` |
| 3 | `frontend/src/main.tsx` | 84 | `fetch("/api/v1/auth/session", { method: "POST" })` с 12 retry |

- **Суть:** Эти вызовы обходят axios interceptors (error handling, auth headers). Ошибки молча проглатываются в `.catch(() => ...)`.
- **Действие:** Заменить на вызовы через `api` (axios instance). Retry-логику из `main.tsx` перенести в axios interceptor или оставить, но с `api.post(...)`.

---

## ГРУППА 6: Инфраструктура и конфигурация

**Приоритет: низкий (dev environment)**

### 6.1. Keycloak redirect URIs захардкожены на localhost

- **Файл:** `docker/keycloak-init.sh:47-48, 55-56`
- **Суть:** `redirectUris` и `webOrigins` указывают на `http://localhost:5173`. Для деплоя нужно параметризовать.
- **Действие:** Вынести в env-переменные `$FRONTEND_URL`.

### 6.2. CORS захардкожен на localhost

- **Файл:** `docker/.env.example:32`
- **Суть:** `CORS_ALLOWED_ORIGINS=http://localhost:5173` — не проблема для dev, но нужен комментарий.
- **Действие:** Добавить комментарий в `.env.example` о необходимости изменения для production.

### 6.3. `sslRequired=none` в Keycloak

- **Файл:** `docker/keycloak-init.sh:34, 36`
- **Суть:** Отключён SSL для Keycloak — ок для dev, но не для prod.
- **Действие:** Параметризовать через env `$KC_SSL_REQUIRED` с default `external`.

### 6.4. Пустой `KEYCLOAK_CLIENT_SECRET` и `KEYCLOAK_BOOTSTRAP_PASSWORD`

- **Файл:** `docker/.env.example:16, 40`
- **Суть:** Пустые значения — пользователь может забыть заполнить.
- **Действие:** Добавить validation в `backend/scripts/bootstrap.py` или docker-entrypoint.

---

## ГРУППА 7: Нереализованные фичи (backend есть, frontend нет)

**Приоритет: требует product-решения**

| # | Backend endpoints | Файл | Статус frontend |
|---|---|---|---|
| 1 | CRUD расписания: `GET/PUT/DELETE /flows/{id}/schedule` | `backend/src/api/v1/schedules.py:55-170` | Только validate вызывается (`ScheduleBuilder.tsx:30`). Нет UI для создания/редактирования/удаления расписаний |
| 2 | Список уведомлений: `GET /notifications` | `backend/src/api/v1/notifications.py:30` | Только badge с count (`NotificationBell.tsx`). Нет страницы списка уведомлений |
| 3 | Preview data: `GET /flows/{id}/preview/{session}/data` | `backend/src/api/v1/preview.py:99` | `Preview.tsx` компонент существует, но не рендерится в UI. `FlowDetail.tsx` импортирует, но не показывает |
| 4 | Tenant alias: `GET /auth/tenant` | `backend/src/api/v1/auth.py:219` | Дублирует `/auth/workspace`. Нигде не используется на frontend |

**Действие:** Для каждого пункта — product-решение: либо дореализовать frontend, либо удалить неиспользуемые backend endpoints.

---

## Сводная таблица

| Группа | Задач | Файлов к изменению | Оценка |
|---|---|---|---|
| 1. Баги | 3 | 3 | 30 мин |
| 2. Dead code | 6 удалений | 4 | 30 мин |
| 3. Дублирование backend | 3 рефакторинга | 8 | 1.5 часа |
| 4. Дублирование frontend | 3 рефакторинга | 10 | 2 часа |
| 5. Frontend reliability | 4 фикса | 5 | 1 час |
| 6. Инфраструктура | 4 доработки | 3 | 30 мин |
| 7. Нереализованные фичи | 4 решения | — | Product decision |

---

## Product Decisions

### PD-1. `KEYCLOAK_CLIENT_SECRET` оставляем опциональным

- **Статус:** принято
- **Причина:** текущий Keycloak-клиент создаётся как `publicClient=true` в `docker/keycloak-init.sh`, поэтому обязательная валидация `KEYCLOAK_CLIENT_SECRET` для dev-контура не нужна и была бы ложным требованием.

### PD-2. `KEYCLOAK_BOOTSTRAP_PASSWORD` для dev допускается пустым

- **Статус:** принято
- **Причина:** в `docker/keycloak-init.sh` уже используется fallback `KEYCLOAK_BOOTSTRAP_PASSWORD:-$ADMIN_PASSWORD`. Для локального dev это приемлемо; отдельную жёсткую validation не добавляем.

### PD-3. Полный UI для CRUD расписаний выносим в отдельный scope

- **Статус:** отложено
- **Причина:** это не багфикс, а отдельная пользовательская функция. В рамках текущего scope оставляем backend CRUD и исправленный `POST /schedules/validate`, но не добавляем экранов создания/редактирования/удаления расписаний без отдельной product-задачи.

### PD-4. Дублирующий `/auth/tenant` удаляем

- **Статус:** принято и выполнено
- **Причина:** endpoint дублировал `/auth/workspace` и не использовался frontend'ом.

### PD-5. Пункты про notifications и preview считать устаревшими

- **Статус:** принято
- **Причина:** список уведомлений уже реализован через `NotificationList`, а `Preview` уже рендерится в `FlowDetail`.
