# Contributing

Thank you for improving Jev Compiler. Keep pull requests focused, explain user-visible behavior, and
never include credentials, private specifications, provider recordings, or generated `.jevcompiler/`
workspace content.

Use Python 3.11 or newer, Node.js 22, and `uv`.

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
```

## Find a first contribution

Browse the [`good first issue`](https://github.com/triggeredcode/jev-compiler/issues?q=is%3Aissue%20state%3Aopen%20label%3A%22good%20first%20issue%22)
or [`help wanted`](https://github.com/triggeredcode/jev-compiler/issues?q=is%3Aissue%20state%3Aopen%20label%3A%22help%20wanted%22)
queues for contained, non-blocking improvements. Before starting:

1. Comment on the issue so work is not duplicated.
2. Keep the pull request scoped to one issue and avoid unrelated cleanup.
3. Ask in the issue if an acceptance criterion or boundary is unclear.

A contribution is ready when its acceptance criteria are met, relevant tests and documentation are
updated, and the checks below pass. Examples, logs, and fixtures must not contain credentials or
private `.jevcompiler/` workspace content.

## Change guidelines

- Use a short-lived branch and small, understandable commits.
- Keep the CLI runnable and tests green after each functional change.
- Add model validation, interpreter coverage, unsafe-input rejection tests, and documentation for
  new DSL features.
- Implement the provider protocol, avoid logging credentials, and use mocked HTTP tests for new
  providers.
- Update `CHANGELOG.md` for user-visible behavior.
- Do not add dependencies unless the standard library or an existing dependency cannot reasonably
  solve the problem.

Open a pull request using the repository template. CI tests Python 3.11–3.13 on Linux, macOS, and
Windows, then builds and inspects both distribution formats.

## Release checks

Build and inspect both distribution formats before creating a release:

```bash
uv build
uv run python scripts/verify_distribution.py dist
```

The verifier checks package metadata, the console entry point, typed-package marker, TypeScript
runtime, and the absence of private workspace files, environment files, specifications, caches, and
bytecode. CI also installs the wheel into a clean virtual environment and runs the packaged CLI.

Maintainers create releases from annotated version tags. The tag must match the package version;
the release workflow repeats validation, builds the distributions, attests them, and publishes them
as GitHub release assets.
