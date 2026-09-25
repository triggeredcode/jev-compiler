# Quickstart

This guide starts with the fully offline showcase, then introduces live TypeSafe execution and the
local-first compiler workflow.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js 22 when validating the generated TypeScript runtime

Clone the repository and install its development environment:

```bash
git clone https://github.com/triggeredcode/jev-compiler.git
cd jev-compiler
uv sync --extra dev
```

## 1. Run the credential-free showcase

```bash
uv run jevcompiler showcase
```

This command loads committed expense-approval fixtures, evaluates the expected decision, freezes a
deployment artifact, and verifies its file digests. It makes no network calls and records
`live_calls: 0`.

The default output is `.jevcompiler/artifacts/expense-approval/showcase/`. Frozen destinations are
immutable; use `--output <path>` when you need a fresh destination.

To see how an application loads that output without importing compiler source code, run the
[offline frozen-artifact consumer](../examples/frozen-consumer/README.md). It uses the generated
TypeScript runtime, a recorded provider callback, and no credentials or network access.

## 2. Validate and run a program

```bash
uv run jevcompiler validate examples/support-routing/task.yaml --kind task
uv run jevcompiler validate examples/support-routing/program.yaml --kind program
uv run jevcompiler run examples/support-routing/program.yaml \
  examples/support-routing/state.json \
  --answers examples/support-routing/answers.json
```

The recorded answers keep this path deterministic and offline.

## 3. Check local model availability

```bash
uv run jevcompiler doctor
```

For scripts, support bundles, and automated setup checks, request one JSON object instead of the
interactive table:

```bash
uv run jevcompiler doctor --json
```

The versioned JSON payload includes every checked provider, its availability, endpoint, discovered
models, redacted failure reason, and the selected teacher when one is available.

The compiler selects teachers in this order:

1. Ollama at `127.0.0.1:11434`
2. LM Studio at `127.0.0.1:1234`
3. OpenRouter's free router when `OPENROUTER_API_KEY` is set
4. A paid OpenRouter model only after explicit opt-in

The doctor command reports availability without printing credentials. A non-free OpenRouter model
requires both an explicit model override and `--allow-paid`; it is never selected automatically.

## 4. Build an optimized artifact

```bash
uv run jevcompiler build examples/support-routing/task.yaml --budget quick
```

The build runs dataset generation, baseline compilation, optimization, held-out evaluation, and
artifact freezing in dependency order. Validated phase output is reused when its inputs and budget
still match.

Use `--budget standard` for semantic rewrites and a broader search or `--budget deep` for the largest
built-in evidence and search budget. Add `--adaptive-cases 4` for one bounded failure-directed
improvement round.

## 5. Inspect and verify output

```bash
uv run jevcompiler artifact verify \
  .jevcompiler/artifacts/support-router/frozen/<candidate-id>
uv run jevcompiler report \
  .jevcompiler/artifacts/support-router/frozen/<candidate-id>
```

Verification checks the manifest and every recorded digest. The report is a self-contained HTML file
with baseline/final metrics, generation history, Pareto trade-offs, lineage, and failure evidence.

## Live TypeSafe execution

The offline commands above do not need a key. To replace recorded answers with a live Jev call:

1. Sign in to the [TypeSafe dashboard](https://console.typesafe.ai/) and get an API key.
2. Export that key as `TYPESAFE_API_KEY`.
3. Omit `--answers` when running the program.

TypeSafe's [official quickstart](https://docs.typesafe.ai/introduction/quickstart) covers the API and
SDK setup in more detail.

```bash
export TYPESAFE_API_KEY="..."
uv run jevcompiler run examples/support-routing/program.yaml \
  examples/support-routing/state.json
```

`TYPESAFE_API_KEY` is a TypeSafe credential; Jev Compiler does not issue a separate key. Never add
keys to tracked files. Generated recordings are stored under `.jevcompiler/cache/`, which is ignored.
Use `--cache-mode replay_only` to require cached responses and fail closed instead of making a live
request.

## Run phases independently

```bash
uv run jevcompiler dataset build examples/support-routing/task.yaml \
  --normal 8 --boundary 4 --semantic-variation 4
uv run jevcompiler baseline build \
  examples/support-routing/task.yaml \
  .jevcompiler/artifacts/support-router/dataset
uv run jevcompiler optimize run \
  .jevcompiler/artifacts/support-router/baseline/program.yaml \
  .jevcompiler/artifacts/support-router/dataset
uv run jevcompiler artifact freeze \
  .jevcompiler/artifacts/support-router/optimization/optimization.json \
  .jevcompiler/artifacts/support-router/dataset
```

After optimization, `jevcompiler dataset adapt` can generate bounded train-only evidence from the
selected failure corpus. Development and test splits remain unchanged.
