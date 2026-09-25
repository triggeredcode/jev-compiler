# Releasing

Releases are built from annotated version tags by GitHub Actions. The workflow validates the tag,
runs the full test suite, builds both distribution formats, verifies their contents, generates
artifact attestations, and publishes a GitHub release.

## Before tagging

1. Ensure `main` is current and its CI run is green.
2. Update `src/jevcompiler/__init__.py` and `CHANGELOG.md` in a dedicated release commit.
3. Run the local release checks:

   ```bash
   uv sync --extra dev --frozen
   uv run ruff check .
   uv run pytest
   uv build
   uv run python scripts/verify_distribution.py dist
   ```

4. Confirm the repository contains no environment files, private specifications, provider
   recordings, or `.jevcompiler/` workspace content.

## Create the release

Use an annotated tag matching the package version, prefixed with `v`:

```bash
git tag -a v0.1.0 -m "Jev Compiler v0.1.0"
git push origin v0.1.0
```

Do not reuse or move a published version tag. If the workflow fails, fix the problem on `main`, bump
the version, and create a new tag.

## Verify the published release

On the GitHub release page, confirm that:

- the workflow completed successfully;
- the wheel and source archive are attached;
- the release notes describe the intended version;
- the artifact attestation exists and identifies this repository and tag;
- installing the wheel in a clean environment exposes the `jevcompiler` command.

Package registry publication is intentionally outside the `v0.1` workflow. GitHub release assets are
the canonical distributions until a registry publishing policy is adopted.
