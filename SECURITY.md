# Security policy

## Reporting

Report vulnerabilities with a
[private GitHub security advisory](https://github.com/triggeredcode/jev-compiler/security/advisories/new).
Do not open a public issue. Include a minimal reproduction, affected version, likely impact, and any
known mitigations, but never include a real credential or unrelated private data.

The maintainers will acknowledge a report as capacity permits, investigate it privately, and publish
a coordinated fix and advisory when warranted. Alpha releases receive security fixes on the latest
release line; older alpha releases are not supported.

## Trust boundaries

- Task and program YAML are untrusted input and are schema-validated.
- Decision expressions are interpreted from an allowlist; Python `eval` is never used.
- Candidate programs cannot run shell commands, import modules, read files, or open sockets.
- API credentials come from environment variables and are redacted from user-facing errors.
- Paid provider fallback is disabled unless the caller explicitly opts in.

Keep credentials, private specifications, sensitive recordings, and provider responses inside the
project-local workspace or another location outside version control.

## Release integrity

Official releases are tagged in this repository. Release assets are built by GitHub Actions from the
tag and include GitHub artifact attestations. Verify the repository, tag, and attestation before
deploying an artifact in a sensitive environment.
