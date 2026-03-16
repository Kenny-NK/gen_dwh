# Swagger Test Scenarios

Ниже минимальный сценарий, который можно повторить в Swagger UI или через curl/Postman.

## Сценарий 1. Bootstrap сессии и выбор workspace

1. Выполните `POST /api/v1/auth/session` с bearer token.
2. Выполните `GET /api/v1/auth/me`.
3. Если `requires_workspace_selection=true`, выполните:
   - `GET /api/v1/auth/workspaces`
   - `POST /api/v1/auth/switch-workspace`
   - `GET /api/v1/auth/workspace`

Пример request body для переключения:

```json
{
  "workspace_id": "c767c7f5-2307-4ec9-83f5-7b194eb4d3e4"
}
```

## Сценарий 2. Создать источник PostgreSQL

1. `POST /api/v1/sources`
2. `GET /api/v1/sources`
3. `POST /api/v1/sources/{source_id}/test`
4. `GET /api/v1/sources/{source_id}/schemas`
5. `GET /api/v1/sources/{source_id}/schemas/public/tables`

Пример request body:

```json
{
  "name": "Postgres ERP",
  "source_type": "postgres",
  "host": "erp-db.internal",
  "port": 5432,
  "database": "erp",
  "username": "readonly_user",
  "password": "change-me",
  "description": "Основная ERP база"
}
```

## Сценарий 3. Создать Jira-источник и проверить preview

1. `POST /api/v1/sources`
2. `GET /api/v1/sources/{source_id}/jira/projects`
3. `GET /api/v1/sources/{source_id}/jira/streams`
4. `PATCH /api/v1/sources/{source_id}/extraction-config`
5. `POST /api/v1/sources/{source_id}/jira/preview`

Пример Jira source:

```json
{
  "name": "Jira Cloud",
  "source_type": "jira",
  "jira_auth_type": "basic_token",
  "host": "https://company.atlassian.net",
  "port": 443,
  "database": "",
  "username": "integration@example.com",
  "password": "jira-api-token",
  "description": "Основной Jira workspace"
}
```

Пример extraction config:

```json
{
  "query_mode": "basic",
  "streams": ["issues", "worklogs"],
  "project_keys": ["DWH", "BI"],
  "start_date": "2026-01-01T00:00:00Z",
  "batch_size": 100,
  "incremental_enabled": true,
  "replication_key": "updated",
  "jql": null
}
```

## Сценарий 4. Создать flow и добавить таблицу

1. `POST /api/v1/flows`
2. `POST /api/v1/flows/{flow_id}/tables`
3. `GET /api/v1/flows/{flow_id}`
4. `GET /api/v1/flows/{flow_id}/tables`
5. `POST /api/v1/flows/{flow_id}/activate`

Пример flow:

```json
{
  "name": "ERP Orders",
  "source_id": "bdaf4b63-d361-4d17-b8b1-cf46fdbb0c39",
  "target_schema": "staging",
  "description": "Ежедневная загрузка заказов",
  "target_table_prefix": "erp",
  "write_mode": "append",
  "preview_mode": "auto"
}
```

Пример table mapping:

```json
{
  "source_schema": "public",
  "source_table": "orders",
  "target_table": "erp_orders",
  "replication_method": "INCREMENTAL",
  "replication_key": "updated_at",
  "selected_columns": ["id", "customer_id", "status", "updated_at"]
}
```

## Сценарий 5. Выполнить preview

1. `POST /api/v1/flows/{flow_id}/preview`
2. Скопируйте `session_id` из ответа.
3. `GET /api/v1/flows/{flow_id}/preview/{session_id}`
4. `GET /api/v1/flows/{flow_id}/preview/{session_id}/data?table=public.orders&page=1&page_size=50`

Пример request body:

```json
{
  "row_limit": 200,
  "tables": ["public.orders"],
  "preview_mode": "snapshot"
}
```

## Сценарий 6. Запустить flow

1. `POST /api/v1/flows/{flow_id}/runs`
2. `GET /api/v1/flows/{flow_id}/runs`
3. `GET /api/v1/runs/{run_id}`
4. При необходимости `POST /api/v1/flows/{flow_id}/runs/{run_id}/cancel`
5. При ошибке `POST /api/v1/flows/{flow_id}/runs/{run_id}/retry`

## Сценарий 7. Настроить расписание

1. `POST /api/v1/schedules/validate`
2. `PUT /api/v1/flows/{flow_id}/schedule`
3. `GET /api/v1/flows/{flow_id}/schedule`
4. `GET /api/v1/schedules`

Пример расписания:

```json
{
  "schedule_type": "cron",
  "cron_expression": "0 */2 * * *",
  "interval_minutes": null,
  "timezone": "Europe/Moscow",
  "max_retries": 5,
  "timeout_minutes": 120
}
```
