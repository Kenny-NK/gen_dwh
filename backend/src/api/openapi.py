"""Central OpenAPI metadata for Swagger UI."""

OPENAPI_DESCRIPTION = """
## Назначение

GenDWH API управляет источниками данных, потоками загрузки, предпросмотром, расписаниями и
запусками пайплайнов в tenant-aware окружении.

## Как тестировать API в Swagger

1. Получите Keycloak access token вне Swagger UI.
2. Выполните `POST /api/v1/auth/session` с заголовком `Authorization: Bearer <token>`.
3. Если ответ вернул `requires_workspace_selection=true`, вызовите:
   - `GET /api/v1/auth/workspaces`
   - `POST /api/v1/auth/switch-workspace`
4. После выбора workspace можно тестировать остальные endpoint'ы.

Примечания:

- Большинство endpoint'ов принимают либо bearer token, либо backend session cookie.
- Swagger UI обычно сохраняет cookie автоматически после успешного вызова `/auth/session`.
- Все UUID и payload examples ниже тестовые и могут быть использованы как шаблон.

## Рекомендуемый сценарий изучения

1. `Auth` — авторизация и выбор workspace.
2. `Sources` и `Jira` — создание и проверка источников.
3. `Flows` и `Preview` — настройка потока и проверка данных.
4. `Schedules` и `Runs` — запуск и автоматизация.
5. `Dashboard`, `Notifications`, `Audit`, `Admin` — эксплуатационные и административные функции.
"""

OPENAPI_TAGS = [
    {
        "name": "Auth",
        "description": (
            "Авторизация, bootstrap backend-сессии и выбор активного workspace. "
            "Начинайте тестирование API с этой категории."
        ),
    },
    {
        "name": "Sources",
        "description": (
            "CRUD и диагностика источников данных: PostgreSQL, S3 и Jira. "
            "Здесь создаются подключения и проверяется доступность источника."
        ),
    },
    {
        "name": "Jira",
        "description": (
            "Jira-специфичные endpoint'ы: проекты, доступные stream'ы, схема stream'ов, "
            "preview и extraction config."
        ),
    },
    {
        "name": "Flows",
        "description": (
            "Управление потоками загрузки и таблицами в потоке. "
            "После создания source обычно следующий шаг находится здесь."
        ),
    },
    {
        "name": "Preview",
        "description": (
            "Предпросмотр данных до запуска полной загрузки. Поддерживает live/snapshot режимы "
            "и маскирование чувствительных полей."
        ),
    },
    {
        "name": "Runs",
        "description": (
            "Ручной запуск, отмена, повторный запуск и просмотр истории выполнения потоков."
        ),
    },
    {
        "name": "Schedules",
        "description": (
            "Настройка cron/interval/manual расписаний и валидация cron-выражений."
        ),
    },
    {
        "name": "Dashboard",
        "description": "Сводные числовые показатели для домашнего экрана приложения.",
    },
    {
        "name": "Notifications",
        "description": "Пользовательские уведомления о событиях и фоновых действиях.",
    },
    {
        "name": "Audit",
        "description": (
            "Журнал аудита изменений в tenant scope. Полезен для расследования действий "
            "пользователей и отладки бизнес-процессов."
        ),
    },
    {
        "name": "Admin",
        "description": (
            "Системное администрирование tenants, пользователей и memberships. "
            "Требует прав системного администратора."
        ),
    },
    {
        "name": "Observability",
        "description": "Технические endpoint'ы готовности сервиса и Prometheus-метрик.",
    },
]

OPENAPI_SERVERS = [
    {
        "url": "/",
        "description": "Текущая среда, из которой открыт Swagger UI.",
    },
    {
        "url": "http://localhost:8000",
        "description": "Локальный backend в Docker Compose.",
    },
]

SWAGGER_UI_PARAMETERS = {
    "displayRequestDuration": True,
    "docExpansion": "list",
    "defaultModelsExpandDepth": -1,
    "persistAuthorization": True,
}
