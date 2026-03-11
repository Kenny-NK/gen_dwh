#!/bin/sh
set -eu

: "${VAULT_ADDR:?VAULT_ADDR is required}"
: "${VAULT_ROOT_TOKEN_FILE:?VAULT_ROOT_TOKEN_FILE is required}"
: "${VAULT_KV_MOUNT:=secret}"
: "${VAULT_KV_VERSION:=v2}"
: "${VAULT_APPROLE_MOUNT:=approle}"
: "${VAULT_APPROLE_NAME:=gendwh-jira-client}"
: "${VAULT_APPROLE_POLICY_NAME:=gendwh-jira-client}"
: "${VAULT_APPROLE_ROLE_ID_FILE:=/opt/gendwh/secrets/vault_role_id}"
: "${VAULT_APPROLE_SECRET_ID_FILE:=/opt/gendwh/secrets/vault_secret_id}"
: "${VAULT_JIRA_CLIENT_CERT_SECRET_PATH:?VAULT_JIRA_CLIENT_CERT_SECRET_PATH is required}"
: "${VAULT_BOOTSTRAP_JIRA_CLIENT_CERT_FILE:?VAULT_BOOTSTRAP_JIRA_CLIENT_CERT_FILE is required}"
: "${VAULT_BOOTSTRAP_JIRA_CLIENT_CERT_PASSWORD_FILE:?VAULT_BOOTSTRAP_JIRA_CLIENT_CERT_PASSWORD_FILE is required}"

export VAULT_TOKEN="$(tr -d '\n' < "$VAULT_ROOT_TOKEN_FILE")"

if [ -z "$VAULT_TOKEN" ]; then
  echo "Vault root token file is empty" >&2
  exit 1
fi

if [ ! -f "$VAULT_BOOTSTRAP_JIRA_CLIENT_CERT_FILE" ]; then
  echo "Jira client certificate file not found: $VAULT_BOOTSTRAP_JIRA_CLIENT_CERT_FILE" >&2
  exit 1
fi

if [ ! -f "$VAULT_BOOTSTRAP_JIRA_CLIENT_CERT_PASSWORD_FILE" ]; then
  echo "Jira client certificate password file not found: $VAULT_BOOTSTRAP_JIRA_CLIENT_CERT_PASSWORD_FILE" >&2
  exit 1
fi

cert_b64="$(base64 < "$VAULT_BOOTSTRAP_JIRA_CLIENT_CERT_FILE" | tr -d '\n')"
cert_password="$(tr -d '\n' < "$VAULT_BOOTSTRAP_JIRA_CLIENT_CERT_PASSWORD_FILE")"
cert_filename="$(basename "$VAULT_BOOTSTRAP_JIRA_CLIENT_CERT_FILE")"

if [ -z "$cert_b64" ] || [ -z "$cert_password" ]; then
  echo "Jira client certificate bootstrap material is empty" >&2
  exit 1
fi

if [ "$VAULT_KV_VERSION" = "v2" ]; then
  policy_path="path \"${VAULT_KV_MOUNT}/data/${VAULT_JIRA_CLIENT_CERT_SECRET_PATH}\" {\n  capabilities = [\"read\"]\n}\n\npath \"${VAULT_KV_MOUNT}/metadata/${VAULT_JIRA_CLIENT_CERT_SECRET_PATH}\" {\n  capabilities = [\"read\"]\n}\n"
else
  policy_path="path \"${VAULT_KV_MOUNT}/${VAULT_JIRA_CLIENT_CERT_SECRET_PATH}\" {\n  capabilities = [\"read\"]\n}\n"
fi

printf '%b' "$policy_path" | vault policy write "$VAULT_APPROLE_POLICY_NAME" -

vault auth enable -path="$VAULT_APPROLE_MOUNT" approle >/dev/null 2>&1 || true
vault write "auth/${VAULT_APPROLE_MOUNT}/role/${VAULT_APPROLE_NAME}" \
  token_policies="$VAULT_APPROLE_POLICY_NAME" \
  token_ttl="1h" \
  token_max_ttl="4h" \
  secret_id_ttl="24h" >/dev/null

vault kv put "${VAULT_KV_MOUNT}/${VAULT_JIRA_CLIENT_CERT_SECRET_PATH}" \
  p12_base64="$cert_b64" \
  password="$cert_password" \
  filename="$cert_filename" >/dev/null

umask 077
vault read -field=role_id "auth/${VAULT_APPROLE_MOUNT}/role/${VAULT_APPROLE_NAME}/role-id" > "$VAULT_APPROLE_ROLE_ID_FILE"
vault write -f -field=secret_id "auth/${VAULT_APPROLE_MOUNT}/role/${VAULT_APPROLE_NAME}/secret-id" > "$VAULT_APPROLE_SECRET_ID_FILE"
