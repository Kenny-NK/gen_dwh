# Jira Connector

## Overview

`jira` source type supports Jira extraction with two runtime modes:

1. `native`
   Used for `pat_bearer` sources.
   `issues` stream is previewed and loaded into target tables with normalized technical columns.

2. `meltano`
   Used for `basic_token` and `basic_password` sources.
   Preview is normalized, but full physical normalized load parity with native runtime is not part of v1.

Current v1 scope covers only `issues`.

## Supported Flow

1. Create or edit source in UI: `Sources -> New Source -> Jira`
2. Validate credentials
3. Open `Jira Extraction Config`
4. Choose query mode:
   - `Базовые настройки`
   - `JQL запрос`
5. Run preview
6. Create flow
7. Run flow

## Query Modes

### `Базовые настройки`

Available settings:

- `projects`
- `streams`
- `batch size`
- `replication key`
- `incremental`
- `start date`

Behavior:

1. Used for source-driven issue selection.
2. `jql` is ignored in this mode.

### `JQL запрос`

Available settings:

- `streams`
- `jql`
- `batch size`

Behavior:

1. Jira selection is driven only by the entered JQL.
2. Basic filters such as selected projects and start date are ignored.

## Normalized `issues` Columns

Native Jira preview and native Jira load expose stable technical columns for `issues`:

1. `issue_id`
2. `issue_key`
3. `summary`
4. `status_name`
5. `status_category_name`
6. `issue_type_name`
7. `project_id`
8. `project_key`
9. `project_name`
10. `created`
11. `updated`
12. `resolved`
13. `reporter_account_id`
14. `reporter_display_name`
15. `assignee_account_id`
16. `assignee_display_name`
17. `priority_name`
18. `resolution_name`
19. `labels`
20. `components`
21. `fix_versions`
22. `parent_issue_key`
23. `fields_raw`

Raw record payload is still preserved in `_raw` where applicable.

## Source Fields

- `host`: Jira base URL, for example `https://<host>/jira` or `https://<company>.atlassian.net`
- `port`: always `443`
- `username`:
  - required for `basic_token` / `basic_password`
  - optional for `pat_bearer`
- `password`:
  - API token
  - password
  - PAT
- `extraction_config`:
  includes `query_mode`, `streams`, `project_keys`, `batch_size`, `incremental_enabled`, `replication_key`, `start_date`, `jql`

## mTLS Deployment

Some corporate Jira gateways require a client certificate before normal Jira authentication.
For this scenario the connector supports mTLS in both native Jira requests and the Meltano path.

Relevant environment variables:

1. `JIRA_CLIENT_CERT_PATH`
   Path to a client certificate in `PKCS#12` (`.p12` / `.pfx`) or PEM format.
2. `JIRA_CLIENT_KEY_PATH`
   Optional private key path when the client certificate is provided as PEM.
3. `JIRA_CLIENT_CERT_PASSWORD`
   Direct password for encrypted certificate material.
4. `JIRA_CLIENT_CERT_PASSWORD_FILE`
   Preferred production option. Path to a file that contains only the certificate password.
5. `EXTERNAL_CA_BUNDLE_PATH`
   Optional CA bundle for corporate trust roots.

Production recommendation:

1. Mount the certificate into the container from a secret store or protected host volume.
2. Keep the certificate password outside `.env` and pass it through `JIRA_CLIENT_CERT_PASSWORD_FILE`.
3. Do not commit `.p12`, `.pem`, `.key`, or password files into the repository.
4. Prefer Vault-backed delivery for Jira client certificate material in production.

Example:

```env
JIRA_CLIENT_CERT_PATH=/opt/gendwh/certs/jira-client.p12
JIRA_CLIENT_CERT_PASSWORD_FILE=/opt/gendwh/secrets/jira_client_cert_password
EXTERNAL_CA_BUNDLE_PATH=/opt/gendwh/certs/external-ca.pem
```

### Vault-backed mTLS

The connector can fetch Jira client certificate material directly from HashiCorp Vault KV.
When `VAULT_JIRA_CLIENT_CERT_SECRET_PATH` is configured, Vault takes precedence over local
`JIRA_CLIENT_CERT_PATH`.

Supported Vault payload fields:

1. `p12_base64`
   Base64-encoded PKCS#12 bundle
2. `password`
   Password for the bundle
3. `filename`
   Optional original filename
4. `cert_pem`
   Alternative PEM certificate content
5. `key_pem`
   Optional PEM private key when PEM certificate mode is used

Relevant settings:

1. `VAULT_ADDR`
2. `VAULT_AUTH_METHOD=approle`
3. `VAULT_APPROLE_MOUNT`
4. `VAULT_ROLE_ID` or `VAULT_ROLE_ID_FILE`
5. `VAULT_SECRET_ID` or `VAULT_SECRET_ID_FILE`
6. `VAULT_KV_MOUNT`
7. `VAULT_KV_VERSION`
8. `VAULT_JIRA_CLIENT_CERT_SECRET_PATH`

`VAULT_TOKEN` or `VAULT_TOKEN_FILE` should be treated as bootstrap or fallback-only options.
Production runtime should use AppRole, Vault Agent, or another non-root Vault auth method.

Example KV v2 secret path:

```text
secret/data/gendwh/jira/client-cert
```

Example secret fields:

```json
{
  "p12_base64": "<base64 PKCS#12 bundle>",
  "password": "<bundle password>",
  "filename": "jira-client.p12"
}
```

## API Endpoints

- `GET /api/v1/sources/{source_id}/jira/projects`
- `GET /api/v1/sources/{source_id}/jira/streams`
- `GET /api/v1/sources/{source_id}/jira/streams/{name}/schema`
- `PATCH /api/v1/sources/{source_id}/extraction-config`
- `POST /api/v1/sources/{source_id}/jira/preview`

Preview response includes:

1. `effective_query_mode`
2. `effective_jql`
3. `columns_by_stream`
4. `rows_by_stream`
5. `schema_by_stream`

Backward-compatible fields `records` and `schema` are still present.

## v1 Constraints

1. Only `issues` is in scope for normalized extraction.
2. Derived metrics such as `Lead Time` are not calculated by the connector.
3. Human-friendly business aliases are not produced in v1.
4. Custom Jira field expansion is not part of v1.
5. Full normalized physical load parity for `meltano` runtime is not part of v1.

## Manual Smoke Checklist

Use this checklist against a real Jira source before release:

### Source Validation

1. Create Jira source with `pat_bearer`
2. Validate credentials successfully
3. Create Jira source with `basic_token` or `basic_password`
4. Validate credentials successfully
5. If corporate Jira requires client certificates, verify the source also validates with the
   mounted mTLS certificate enabled

### Basic Query Mode

1. Open `Jira Extraction Config`
2. Select `Базовые настройки`
3. Pick project(s)
4. Leave `jql` empty
5. Run preview
6. Verify:
   - preview succeeds
   - `issues` rows are tabular
   - columns include `issue_key`, `summary`, `status_name`, `resolved`
   - effective mode is `basic`

### JQL Query Mode

1. Switch to `JQL запрос`
2. Enter JQL, for example:
   `project = DWHTOT AND resolved >= "2025-11-01" AND resolved <= "2025-11-30" AND status != "Cancelled" ORDER BY created DESC`
3. Keep selected projects unchanged on purpose
4. Run preview
5. Verify:
   - preview succeeds
   - effective mode is `jql`
   - effective JQL is shown
   - selected projects do not affect the result

### Flow Creation

1. Create flow from Jira source
2. Verify flow persists `query_mode`
3. Verify stale preview is cleared after config changes

### Native Runtime Load

1. Run flow for `pat_bearer`
2. Verify target table contains normalized issue columns
3. Verify `_raw` exists
4. Verify `fields_raw` exists

### Meltano Runtime Check

1. Run flow for `basic_token` or `basic_password`
2. Verify preview still works in normalized form
3. Verify load behavior matches current v1 limitation notes

## Notes

1. Deleting Jira source with active flows is blocked.
2. Credentials changes are audited with redacted payload.
3. Existing `postgres` and `s3` source behavior is preserved.
