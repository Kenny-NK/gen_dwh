Place additional corporate CA certificates and local-only Jira client certificates in this directory.

Files in this directory are ignored by git except for this `README.md` and `.gitignore`.

Supported local files:

1. `external-ca.pem`
   Mounted into backend and worker containers and appended to the default public CA trust
   store at runtime. Add only CA certificates here, not leaf server certificates.

2. `jira-client.p12` or `jira-client.pem`
   Optional Jira client certificate for mTLS access. This file must stay local and must not
   be committed.

Recommended production pattern:

1. Mount the client certificate from a secret store or host volume.
2. Provide its path through `JIRA_CLIENT_CERT_PATH`.
3. Provide the password through `JIRA_CLIENT_CERT_PASSWORD_FILE` rather than a plain env var.
