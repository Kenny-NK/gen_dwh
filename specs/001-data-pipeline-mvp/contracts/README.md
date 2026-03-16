# Legacy Contracts

Файлы в этой директории сохранены как исторические YAML-контракты MVP и больше не считаются
источником истины для Swagger/OpenAPI.

Актуальный источник истины:

- backend-код FastAPI в `backend/src`
- живая схема `GET /openapi.json`
- Swagger UI `GET /docs`

Почему это важно:

- runtime API уже использует backend session cookie и workspace switching;
- часть legacy-контрактов все еще описывает `X-Tenant-ID`, `/auth/tenant` и устаревшие поля;
- ручная поддержка этих YAML без генерации из кода приводит к расхождениям.

Практическое правило:

- для разработки, тестирования и интеграций используйте `/openapi.json`;
- legacy YAML держите только как reference на ранний MVP-дизайн.
