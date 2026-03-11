`docker/vault` contains local bootstrap assets for Vault-based secret delivery.

Current flow:

1. `vault` starts as a local development Vault instance for compose-based testing.
2. `vault-init` uses the local root token only for bootstrap tasks.
3. `vault-init` reads the local Jira client certificate bootstrap files from git-ignored
   `docker/certs` and `docker/secrets`.
4. `vault-init` writes the Jira client certificate bundle into Vault KV under the configured
   secret path.
5. `vault-init` creates a least-privilege policy and an AppRole for application runtime.
6. Application containers fetch Jira client certificate material from Vault via AppRole auth.

For production:

1. Do not use the local dev Vault mode.
2. Point the application to a managed or HA Vault deployment.
3. Provision Jira certificate material into Vault through your operational secret workflow.
4. Use AppRole, Vault Agent, Kubernetes auth, or another workload identity flow instead of
   root tokens.
