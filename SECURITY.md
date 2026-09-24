# Security policy

## Reporting

Please report vulnerabilities privately to the repository owner before opening a public issue.
Include a minimal reproduction, affected version, and likely impact.

## Trust boundaries

- Task and program YAML are untrusted input and are schema-validated.
- Decision expressions are interpreted from an allowlist; Python `eval` is never used.
- Candidate programs cannot run shell commands, import modules, read files, or open sockets.
- API credentials come from environment variables and are redacted from user-facing errors.
- Paid provider fallback is disabled unless the caller explicitly opts in.

Keep credentials, private specifications, sensitive recordings, and provider responses inside the
project-local workspace or another location outside version control.
