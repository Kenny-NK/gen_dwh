# Swagger Roadmap

Статус работ по приведению Swagger/OpenAPI к production-уровню.

## Пункты

1. `completed` Добавить единые error schemas и `responses` для кодов `400/401/403/404/409/422/503`.
2. `completed` Явно оформить security schemes: bearer token и backend session cookie.
3. `completed` Заменить оставшиеся raw `dict` response на явные Pydantic response models.
4. `completed` Добавить examples для query/path параметров на ключевых endpoint'ах.
5. `completed` Синхронизировать или пометить устаревшими старые `specs/contracts`.
6. `completed` Проверить реальный `openapi.json` на поднятом backend и убедиться, что схема рендерится корректно.
7. `completed` Кастомизировать Swagger UI и `servers` под локальную среду и эксплуатацию.

## Порядок выполнения

Все 7 пунктов закрыты.
