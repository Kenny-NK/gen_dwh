Place additional corporate CA certificates in this directory as PEM files.

`external-ca.pem` is mounted into backend and worker containers and appended to the
default public CA trust store at runtime. Add only CA certificates here, not leaf
server certificates.
