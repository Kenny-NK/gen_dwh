#!/usr/bin/env bash
set -euo pipefail

KCADM="/opt/keycloak/bin/kcadm.sh"
SERVER_URL="${KEYCLOAK_INTERNAL_URL:-http://keycloak:8080}"
ADMIN_REALM="${KEYCLOAK_ADMIN_REALM:-master}"
REALM_NAME="${KEYCLOAK_REALM:-gendwh}"
CLIENT_ID="${KEYCLOAK_CLIENT_ID:-gendwh-app}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:5173}"
KC_SSL_REQUIRED="${KC_SSL_REQUIRED:-external}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:?KEYCLOAK_ADMIN_PASSWORD is required}"
BOOTSTRAP_USER="${KEYCLOAK_BOOTSTRAP_USER:-admin}"
BOOTSTRAP_PASSWORD="${KEYCLOAK_BOOTSTRAP_PASSWORD:-$ADMIN_PASSWORD}"
BOOTSTRAP_EMAIL="${KEYCLOAK_BOOTSTRAP_EMAIL:-admin@gendwh.local}"

# Keycloak can report healthy slightly before admin endpoints are ready.
for _ in {1..30}; do
  if "$KCADM" config credentials \
    --server "$SERVER_URL" \
    --realm "$ADMIN_REALM" \
    --user "$ADMIN_USER" \
    --password "$ADMIN_PASSWORD" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

"$KCADM" config credentials \
  --server "$SERVER_URL" \
  --realm "$ADMIN_REALM" \
  --user "$ADMIN_USER" \
  --password "$ADMIN_PASSWORD" >/dev/null

if ! "$KCADM" get "realms/$REALM_NAME" >/dev/null 2>&1; then
  "$KCADM" create realms -s "realm=$REALM_NAME" -s enabled=true -s "sslRequired=$KC_SSL_REQUIRED" >/dev/null
fi
"$KCADM" update "realms/$REALM_NAME" -s "sslRequired=$KC_SSL_REQUIRED" -s enabled=true >/dev/null

client_uuid=$("$KCADM" get clients -r "$REALM_NAME" -q "clientId=$CLIENT_ID" --fields id --format csv --noquotes | tail -n1 || true)
if [ -z "$client_uuid" ]; then
  "$KCADM" create clients -r "$REALM_NAME" \
    -s "clientId=$CLIENT_ID" \
    -s enabled=true \
    -s protocol=openid-connect \
    -s publicClient=true \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=true \
    -s "redirectUris=[\"$FRONTEND_URL\",\"$FRONTEND_URL/*\"]" \
    -s "webOrigins=[\"$FRONTEND_URL\"]" >/dev/null
else
  "$KCADM" update "clients/$client_uuid" -r "$REALM_NAME" \
    -s enabled=true \
    -s publicClient=true \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=true \
    -s "redirectUris=[\"$FRONTEND_URL\",\"$FRONTEND_URL/*\"]" \
    -s "webOrigins=[\"$FRONTEND_URL\"]" >/dev/null
fi

user_uuid=$("$KCADM" get users -r "$REALM_NAME" -q "username=$BOOTSTRAP_USER" --fields id --format csv --noquotes | tail -n1 || true)
if [ -z "$user_uuid" ]; then
  "$KCADM" create users -r "$REALM_NAME" \
    -s "username=$BOOTSTRAP_USER" \
    -s "email=$BOOTSTRAP_EMAIL" \
    -s firstName=Admin \
    -s lastName=User \
    -s emailVerified=true \
    -s enabled=true >/dev/null
  user_uuid=$("$KCADM" get users -r "$REALM_NAME" -q "username=$BOOTSTRAP_USER" --fields id --format csv --noquotes | tail -n1)
fi

"$KCADM" update "users/$user_uuid" -r "$REALM_NAME" \
  -s "email=$BOOTSTRAP_EMAIL" \
  -s firstName=Admin \
  -s lastName=User \
  -s emailVerified=true \
  -s enabled=true >/dev/null

"$KCADM" set-password -r "$REALM_NAME" --userid "$user_uuid" --new-password "$BOOTSTRAP_PASSWORD" >/dev/null

if ! "$KCADM" get "roles/admin" -r "$REALM_NAME" >/dev/null 2>&1; then
  "$KCADM" create roles -r "$REALM_NAME" -s name=admin >/dev/null
fi

"$KCADM" add-roles -r "$REALM_NAME" --uusername "$BOOTSTRAP_USER" --rolename admin >/dev/null || true
"$KCADM" add-roles -r "$REALM_NAME" --uusername "$BOOTSTRAP_USER" --cclientid realm-management --rolename realm-admin >/dev/null || true

echo "Keycloak bootstrap completed: realm=$REALM_NAME client=$CLIENT_ID user=$BOOTSTRAP_USER"
