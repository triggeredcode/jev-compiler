## Summary

Describe the user-visible change and why it is needed.

## Verification

List the commands, fixtures, or manual checks used to verify the change.

## Checklist

- [ ] The change is focused and contains no credentials, private specifications, recordings, or generated workspace artifacts.
- [ ] Tests cover new behavior and unsafe-input rejection where applicable.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run pytest` passes.
- [ ] Public documentation and `CHANGELOG.md` are updated when behavior changes.
- [ ] Provider changes use mocked HTTP tests and do not log credentials.
- [ ] Artifact or packaging changes pass `uv build` and `uv run python scripts/verify_distribution.py dist`.
