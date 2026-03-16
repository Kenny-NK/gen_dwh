# GenDWH API Map

Этот файл дополняет Swagger UI и помогает быстро понять порядок изучения API.

## 1. Auth

- `POST /api/v1/auth/session` — bootstrap backend session по Keycloak bearer token
- `DELETE /api/v1/auth/session` — очистить backend session cookie
- `GET /api/v1/auth/me` — получить текущий auth context
- `GET /api/v1/auth/workspaces` — список доступных workspace
- `POST /api/v1/auth/switch-workspace` — выбрать активный workspace
- `GET /api/v1/auth/workspace` — получить текущий активный workspace

Пример:

```bash
curl -X POST http://localhost:8000/api/v1/auth/session \
  -H 'Authorization: Bearer <KEYCLOAK_ACCESS_TOKEN>' \
  -c cookies.txt
```

## 2. Sources

- `GET /api/v1/sources`
- `POST /api/v1/sources`
- `POST /api/v1/sources/test-connection`
- `GET /api/v1/sources/{source_id}`
- `PATCH /api/v1/sources/{source_id}`
- `DELETE /api/v1/sources/{source_id}`
- `POST /api/v1/sources/{source_id}/test`
- `GET /api/v1/sources/{source_id}/schemas`
- `GET /api/v1/sources/{source_id}/schemas/{schema_name}/tables`

Пример:

```bash
curl -X POST http://localhost:8000/api/v1/sources \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <KEYCLOAK_ACCESS_TOKEN>' \
  -d '{
    "name": "Postgres ERP",
    "source_type": "postgres",
    "host": "erp-db.internal",
    "port": 5432,
    "database": "erp",
    "username": "readonly_user",
    "password": "change-me"
  }'
```

## 3. Jira

- `GET /api/v1/sources/{source_id}/jira/projects`
- `GET /api/v1/sources/{source_id}/jira/streams`
- `GET /api/v1/sources/{source_id}/jira/streams/{stream_name}/schema`
- `PATCH /api/v1/sources/{source_id}/extraction-config`
- `POST /api/v1/sources/{source_id}/jira/preview`

## 4. Flows

- `GET /api/v1/flows`
- `POST /api/v1/flows`
- `GET /api/v1/flows/{flow_id}`
- `PATCH /api/v1/flows/{flow_id}`
- `DELETE /api/v1/flows/{flow_id}`
- `POST /api/v1/flows/{flow_id}/activate`
- `POST /api/v1/flows/{flow_id}/pause`
- `GET /api/v1/flows/{flow_id}/tables`
- `POST /api/v1/flows/{flow_id}/tables`
- `PATCH /api/v1/flows/{flow_id}/tables/{table_id}`
- `DELETE /api/v1/flows/{flow_id}/tables/{table_id}`

Пример:

```bash
curl -X POST http://localhost:8000/api/v1/flows \
  -H 'Content-Type: application/json' \
  -b cookies.txt \
  -d '{
    "name": "ERP Orders",
    "source_id": "bdaf4b63-d361-4d17-b8b1-cf46fdbb0c39",
    "target_schema": "staging",
    "target_table_prefix": "erp",
    "write_mode": "append",
    "preview_mode": "auto"
  }'
```

## 5. Preview

- `POST /api/v1/flows/{flow_id}/preview`
- `GET /api/v1/flows/{flow_id}/preview/{session_id}`
- `GET /api/v1/flows/{flow_id}/preview/{session_id}/data`

## 6. Runs

- `GET /api/v1/flows/{flow_id}/runs`
- `POST /api/v1/flows/{flow_id}/runs`
- `GET /api/v1/flows/{flow_id}/runs/{run_id}`
- `POST /api/v1/flows/{flow_id}/runs/{run_id}/cancel`
- `POST /api/v1/flows/{flow_id}/runs/{run_id}/retry`
- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`

## 7. Schedules

- `GET /api/v1/flows/{flow_id}/schedule`
- `PUT /api/v1/flows/{flow_id}/schedule`
- `DELETE /api/v1/flows/{flow_id}/schedule`
- `POST /api/v1/flows/{flow_id}/schedule/validate`
- `POST /api/v1/schedules/validate`
- `GET /api/v1/schedules`

## 8. Dashboard

- `GET /api/v1/dashboard/stats`

## 9. Notifications

- `GET /api/v1/notifications`
- `GET /api/v1/notifications/count`
- `POST /api/v1/notifications/{notification_id}/read`
- `POST /api/v1/notifications/read-all`

## 10. Audit

- `GET /api/v1/audit`

## 11. Admin

- `GET /api/v1/admin/tenants`
- `POST /api/v1/admin/tenants`
- `PATCH /api/v1/admin/tenants/{tenant_id}`
- `DELETE /api/v1/admin/tenants/{tenant_id}`
- `GET /api/v1/admin/users`
- `POST /api/v1/admin/users`
- `PATCH /api/v1/admin/users/{user_id}`
- `DELETE /api/v1/admin/users/{user_id}`
- `PUT /api/v1/admin/users/{user_id}/memberships`
- `DELETE /api/v1/admin/users/{user_id}/memberships/{membership_id}`

## 12. Observability

- `GET /health`
- `GET /metrics`
