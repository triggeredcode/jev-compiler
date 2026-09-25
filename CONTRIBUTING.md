# Contributing

Use Python 3.11 or newer and `uv`.

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
```

Keep changes small and leave the CLI runnable and tests green. New DSL features must include model
validation, interpreter tests, unsafe-input rejection tests, and documentation. New providers must
implement the protocol, avoid logging credentials, and use mocked HTTP tests.

## Release checks

Build and inspect both distribution formats before creating a release:

```bash
uv build
uv run python scripts/verify_distribution.py dist
```

The verifier checks package metadata, the console entry point, typed-package marker, TypeScript
runtime, and the absence of private workspace files, environment files, specifications, caches,
and bytecode. CI also installs the wheel into a clean virtual environment and runs the packaged CLI.
Publishing is intentionally separate and is not performed by CI.
