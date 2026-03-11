Use this directory only for local, git-ignored secret files that are mounted read-only into
containers under `/opt/gendwh/secrets`.

Recommended files:

1. `jira_client_cert_password`
   Contains only the Jira client certificate password without extra formatting.

2. `vault_token`
   Contains only the Vault bootstrap root token for local `vault-init`. Do not expose it to
   application containers.

3. `vault_role_id`
   AppRole role ID for application runtime access to Vault.

4. `vault_secret_id`
   AppRole secret ID for application runtime access to Vault.

Production recommendation:

1. Replace local files with a secret manager or an equivalent protected volume.
2. Reference mounted secret files through environment variables such as
   `JIRA_CLIENT_CERT_PASSWORD_FILE=/opt/gendwh/secrets/jira_client_cert_password`.
