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

