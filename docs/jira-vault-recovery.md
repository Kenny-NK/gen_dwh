# Jira Vault Recovery

## Когда это нужно

Эта инструкция нужна, если Jira source с `basic_password` или `basic_token` начинает падать на проверке подключения,
хотя логин и пароль корректны.

Для корпоративной Jira в этом проекте сначала используется `mTLS client certificate`, а уже потом обычная Jira
авторизация. Если backend не может получить Jira client certificate из Vault, проверка подключения падает до
проверки логина и пароля.

Типичный симптом в логах backend:

```text
POST http://vault:8200/v1/auth/approle/login -> 403 Forbidden
```

## Причина

Локальный dev Vault работает в `-dev` режиме и не хранит состояние после пересоздания контейнера.  
Если `vault` был пересоздан, а `backend` остался со старыми файлами:

1. `docker/secrets/vault_role_id`
2. `docker/secrets/vault_secret_id`

то AppRole credentials устаревают, и backend больше не может залогиниться в Vault.

## Быстрое восстановление

Из корня проекта:

```bash
docker compose -f docker/docker-compose.yml run --rm vault-init
docker compose -f docker/docker-compose.yml restart backend celery-worker celery-beat
docker compose -f docker/docker-compose.yml ps
```

Ожидаемый результат:

1. `vault-init` завершается с кодом `0`
2. `backend` -> `healthy`
3. `celery-worker` -> `healthy`
4. `celery-beat` -> `healthy`

## Что делает recovery

`vault-init` выполняет заново:

1. создает policy `gendwh-jira-client`
2. включает `approle` auth mount
3. создает роль `gendwh-jira-client`
4. загружает Jira client certificate в `secret/gendwh/jira/client-cert`
5. пересоздает:
   - `docker/secrets/vault_role_id`
   - `docker/secrets/vault_secret_id`

После этого `backend` и `celery` нужно перезапустить, чтобы они перечитали новые AppRole credentials.

## Проверка

Проверить, что AppRole снова существует:

```bash
docker exec gendwh-vault sh -lc '
  export VAULT_ADDR=http://127.0.0.1:8200
  export VAULT_TOKEN=${VAULT_DEV_ROOT_TOKEN:-gendwh-local-vault-root-token-2026}
  vault auth list
'
```

В выводе должен быть `approle/`.

Проверить backend-логи:

```bash
docker compose -f docker/docker-compose.yml logs --tail=100 backend
```

После восстановления там не должно быть повторяющихся:

```text
POST http://vault:8200/v1/auth/approle/login -> 403 Forbidden
```

## Как не ловить это снова

1. Если пересоздаешь `vault`, сразу после этого запускай `vault-init`
2. После `vault-init` перезапускай `backend`, `celery-worker`, `celery-beat`
3. Не считай `docker/secrets/vault_role_id` и `docker/secrets/vault_secret_id` постоянными секретами в dev-среде
4. Для production используй внешний Vault с постоянным storage, а не `vault server -dev`
