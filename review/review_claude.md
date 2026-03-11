# Code Review: GenDWH Project

**Дата:** 2026-03-11
**Ревьюер:** Claude Opus 4.6
**Ветка:** 003-jira-connector (base: 001-data-pipeline-mvp)

## Общая оценка: 6.5 / 10

Проект демонстрирует хорошую архитектурную основу, но имеет существенные пробелы в безопасности, тестировании и production-readiness.

---

## 1. АРХИТЕКТУРА (7/10)

**Сильные стороны:**
- Четкое разделение слоев: `api/` -> `services/` -> `models/` + `middleware/`
- Multi-tenant архитектура через PostgreSQL schemas — грамотный подход
- Dual DB (system + business) — правильная изоляция конфига от данных
- RBAC с fine-grained permissions через `Permission` enum
- Workspace-aware аутентификация с поддержкой ролей на уровне workspace

**Проблемы:**
- **Scheduler слишком толстый** — 779 строк в `scheduler.py`, функция `_execute_flow_run_async` ~400 строк. Нарушает SRP
- **Нет сервисного слоя для auth** — `workspace_auth.py` (432 строки) содержит и бизнес-логику, и DB-запросы, и HTTP exceptions
- **Дублирование `_build_auth_context` и `_build_auth_context_from_workspaces`** — ~80% одинакового кода в `workspace_auth.py:110-180` и `workspace_auth.py:214-246`
- **NullPool** в `base.py:17-22` — каждый запрос открывает новое соединение. Для production нужен connection pooling (AsyncAdaptedQueuePool или PgBouncer)

---

## 2. БЕЗОПАСНОСТЬ (5/10) — КРИТИЧНО

### Критические проблемы:

| Проблема | Файл:строка | Серьёзность |
|---|---|---|
| `verify_aud=False` при валидации JWT | `security.py:96` | **CRITICAL** — aud проверяется вручную, но если `azp` и `aud` оба пустые, токен пройдёт |
| `/health` и `/metrics` без аутентификации | `health.py:87`, `metrics.py:97` | **HIGH** — раскрытие внутреннего состояния (tenant schemas, cleanup jobs, error counts) |
| `_metrics` — dict с in-process счётчиками, не thread-safe | `metrics.py:12-16` | **HIGH** — гонки при `_metrics["requests_total"] += 1` |
| Глобальные мутабельные переменные в `security.py:14-18` | `security.py:14-18` | **MEDIUM** — `_keycloak_failure_count += 1` не атомарен в async |
| Keycloak в `start-dev` режиме | `docker-compose.yml:87` | **HIGH** — отключены security features |
| `AUTH_COOKIE_SECURE=false` по умолчанию | `config.py:31` | **HIGH** — cookies передаются по HTTP |
| Все порты открыты наружу (5432, 15433, 6379, 8080, 9090) | `docker-compose.yml` | **HIGH** — DB и Redis доступны извне |
| `debug` mode раскрывает детали ошибок | `sources.py:371-372` | **MEDIUM** — `f"{detail}: {exc}"` |
| Нет CSRF-защиты | middleware/ | **MEDIUM** — cookie-based auth без CSRF token |

### Положительное:
- Шифрование паролей через pgcrypto (`connection.py:144-159`)
- Валидация слабых секретов при старте (`config.py:80-98`)
- JWKS кеширование с circuit breaker
- Audit logging для мутаций
- Schema name validation через regex (`tenant.py:14,19`)

---

## 3. МОДЕЛИ ДАННЫХ (7.5/10)

**Хорошо:**
- UUID первичные ключи
- Timezone-aware datetime
- Soft deletes (`deleted_at`)
- Индексы на часто запрашиваемых полях
- `UniqueConstraint("flow_id", "run_number")` — грамотная защита
- Advisory locks для конкурентного выполнения flow

**Проблемы:**
- **Magic strings вместо enum**: `"pending"`, `"running"`, `"failed"`, `"draft"`, `"paused"`, `"success"`, `"cancelled"` разбросаны по всему коду. Нужен `StatusEnum`
- **`source_deleted: bool`** в Flow (`flow.py:37-42`) — избыточен при наличии `source_id IS NULL` с `ondelete="SET NULL"`
- **JSONB без типизации**: `extraction_config: Mapped[dict | None]` (`source.py:38`, `flow.py:53`) — нет runtime-валидации содержимого
- **TimestampMixin**: двойной default (`default=now_utc` + `server_default=func.now()`) в `base.py:40-48` — может привести к рассинхрону

---

## 4. СЕРВИСНЫЙ СЛОЙ (6.5/10)

**6446 строк** в 19 сервисных файлах — объём значительный.

**Хорошо:**
- `SourceService` — хорошая инкапсуляция CRUD с валидацией
- `RunService` — graced stale run detection (orphaned, pending, running)
- `ConnectionTestResult` dataclass — чистый контракт
- `auto_commit` параметр — позволяет контролировать транзакции

**Проблемы:**
- **`except Exception` повсюду**: `scheduler.py` содержит ~15 блоков `except Exception`. Теряется контекст ошибок, невозможно различить типы сбоев
- **Нет custom exceptions**: используется `ValueError` для бизнес-ошибок (`source_service.py:76-104`). Нужна иерархия: `SourceNotFoundError`, `ConnectionTestError`, etc.
- **`update_source`** (`source_service.py:281-406`) — 125 строк с `**kwargs`. Сложно тестировать, нет type safety
- **Worker event loop** (`scheduler.py:58-65`) — ручное управление через `global _worker_loop` и `threading.Lock`. Хрупкий паттерн
- **MD5 для advisory lock ID** (`scheduler.py:55`) — не криптографически значимо, но collision risk при int32 truncation

---

## 5. API СЛОЙ (7/10)

**Хорошо:**
- RESTful дизайн с корректными HTTP-кодами
- Permission checking через DI (`Depends(require_permission(...))`)
- Pydantic-схемы для request/response
- Пароли редактируются в audit log (`sources.py:242-244`)
- Пагинация с `limit`/`offset`

**Проблемы:**
- **Schemas в route-файлах** (`sources.py:26-85`) — должны быть в `schemas/`
- **Паттерн `except HTTPException: raise` + `except ValueError` + `except Exception`** повторяется в каждом endpoint (`sources.py:182-187, 261-268, 304-311`) — нужен единый middleware
- **`current_user: dict`** — нетипизированный dict по всему API. Нужен Pydantic model или TypedDict
- **N+1 в `list_sources`** (`sources.py:138-139`) — для каждого source вызывается `_to_source_response` с отдельным запросом `_mask_token`
- **Response interceptor-пустышка** на фронте (`api.ts:57-62`) — `(error) => Promise.reject(error)` ничего не делает

---

## 6. ТЕСТИРОВАНИЕ (4/10) — КРИТИЧНО

### Backend: 17 unit + 6 integration тестов

| Модуль | Тесты | Покрытие |
|---|---|---|
| config | test_config.py | Базовое |
| scheduler | test_scheduler_imports.py, test_scheduler_timezone.py | Только import и timezone |
| jira | test_jira_runtime.py, test_jira_schema.py, test_jira_service.py | Хорошо |
| source_service | test_source_service.py | Есть |
| run_service | test_run_service.py | Есть |
| flow_service | test_flow_service.py | Есть |
| health | test_health.py, test_health_api.py | Есть |
| **scheduler execution** | **НЕТ** | **0%** |
| **connection/encrypt** | **НЕТ** | **0%** |
| **meltano.py (764 строки)** | **test_meltano_metrics.py (только метрики)** | **~5%** |
| **preview.py (602 строки)** | **test_preview_service.py** | Частично |
| **s3_loader (393 строки)** | **НЕТ** | **0%** |

### Frontend: 3 теста
- `api.test.ts`, `formatDate.test.ts`, `runStatus.test.ts`
- **0 тестов компонентов** — ни одного render-теста для React-компонентов
- **0 тестов hooks** (useAuth, useListWithPagination)

### Главная проблема
`conftest.py` — 20 строк, единственная фикстура `client`. Нет:
- DB-фикстур (transaction rollback, factory boy)
- Mock-фикстур для Redis, Keycloak, Meltano
- Tenant context фикстуры
- Authenticated request helpers

---

## 7. FRONTEND (6.5/10)

**Хорошо:**
- React Router с lazy-loaded страницами (`main.tsx:22-31`)
- React Query для серверного состояния
- OIDC-интеграция с MemoryStateStore (не localStorage — безопаснее)
- Session retry с exponential backoff (`main.tsx:84-104`)
- ErrorBoundary + ToastProvider
- Tailwind CSS с dark mode
- i18n-поддержка

**Проблемы:**
- **`[key: string]: unknown`** в интерфейсах (`SourcesList.tsx:27`) — нарушает строгую типизацию
- **Клиентская фильтрация** (`SourcesList.tsx:114-123`) вместо серверной — при 1000+ sources будет проблема
- **Нет роутинга по ролям** — `/admin/users-roles` доступен всем авторизованным (нет проверки permissions на фронте)
- **Нет loading skeletons** — просто `<div>Загрузка...</div>` везде
- **`as AxiosError<ErrorPayload>`** (`api.ts:65`) — unsafe cast без проверки
- **Нет обработки 401** в interceptor — response interceptor пустой (`api.ts:57-62`). При истечении сессии пользователь не перенаправляется на login

---

## 8. DOCKER / ИНФРАСТРУКТУРА (5.5/10)

**Хорошо:**
- Resource limits на всех сервисах
- Health checks на всех сервисах
- Правильная цепочка `depends_on` с conditions
- Business DB с тюнингом PostgreSQL (`shared_buffers`, `wal_compression`)
- Named volumes для persistence
- Prometheus с retention 15d

**Критичные проблемы:**
- **`start-dev`** для Keycloak — отключает security features, HTTPS, hostname validation
- **Все порты открыты наружу** — нет network segmentation
- **Нет reverse proxy** (nginx) — нет TLS termination, нет HTTPS
- **Celery `-P solo`** (`docker-compose.yml:199`) — один процесс, нет параллелизма. Один медленный flow блокирует всё
- **Нет `.dockerignore`** видно в tracked files — вероятно только что добавлены
- **Нет CI/CD** конфигурации

---

## 9. КАЧЕСТВО КОДА (6.5/10)

**Хорошо:**
- Ruff настроен с хорошим набором правил (`pyproject.toml:48`)
- `StrEnum` для Permission — modern Python
- `dataclass(slots=True)` для AuthContext
- Консистентный async/await
- Структурированное логирование через structlog

**Проблемы:**
- **Нет docstrings** на большинстве методов сервисов
- **Смешение русского и английского** в error messages: `"Источник не найден"` vs `"Flow not found"` vs `"Jira connector is disabled"`
- **`dict` вместо typed models** для `current_user` по всей кодовой базе
- **Дублирование нормализации**: `_normalize_jira_auth_type` вызывается в 5+ местах
- **Magic numbers**: `[:2000]` для error truncation (`scheduler.py:259,300`), `[:500]` для health (`health.py:126`), `[:8]` для lock hash (`scheduler.py:55`)
- **Зависимости не закреплены**: `fastapi>=0.109.0` (`pyproject.toml:11`) — может притянуть несовместимую версию

---

## 10. СВОДНАЯ ТАБЛИЦА РИСКОВ

| Категория | Риск | Приоритет |
|---|---|---|
| Security | Открытые порты DB/Redis | **P0** |
| Security | Нет HTTPS/TLS | **P0** |
| Security | Keycloak в dev-режиме | **P0** |
| Security | `/health` + `/metrics` без auth | **P1** |
| Security | Cookie secure=false | **P1** |
| Security | Нет CSRF protection | **P1** |
| Testing | ~4% coverage backend, 0 frontend component tests | **P1** |
| Reliability | NullPool — нет connection pooling | **P1** |
| Reliability | Celery `-P solo` — нет параллелизма | **P1** |
| Reliability | `_metrics` dict — race conditions | **P2** |
| Code Quality | Magic strings вместо enum для статусов | **P2** |
| Code Quality | `except Exception` без специфики | **P2** |
| Code Quality | Scheduler 779 строк, одна функция 400 строк | **P2** |
| Maintainability | Нет CI/CD | **P2** |
| Maintainability | Зависимости не закреплены | **P3** |

---

## РЕКОМЕНДАЦИИ (по приоритету)

### Немедленно (P0):
1. Убрать проброс портов 5432, 15433, 6379 наружу (или ограничить `127.0.0.1:`)
2. Добавить nginx reverse proxy с TLS
3. Переключить Keycloak на `start` с HTTPS

### Ближайшее время (P1):
4. Закрыть `/health` и `/metrics` аутентификацией (или ограничить сетью)
5. Добавить connection pooling вместо NullPool
6. Написать conftest.py с полноценными DB-фикстурами
7. Добавить `AUTH_COOKIE_SECURE=true` для production
8. Реализовать 401-обработку во frontend interceptor
9. Переключить Celery на `prefork` или `gevent` pool

### Средний срок (P2):
10. Ввести `StatusEnum` вместо magic strings
11. Создать иерархию custom exceptions
12. Рефакторинг `scheduler.py` — разбить `_execute_flow_run_async`
13. Типизировать `current_user` через Pydantic/TypedDict
14. Добавить CI/CD pipeline (lint + test + build)

### Долгосрочно (P3):
15. Закрепить версии зависимостей (`uv.lock` уже есть, нужно подключить)
16. Добавить distributed tracing (OpenTelemetry)
17. Secret management (Vault/AWS Secrets Manager)
18. Frontend component tests (Vitest + Testing Library)
