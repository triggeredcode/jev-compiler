# Jev Compiler

[![CI](https://github.com/triggeredcode/jev-compiler/actions/workflows/ci.yml/badge.svg)](https://github.com/triggeredcode/jev-compiler/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/triggeredcode/jev-compiler?display_name=tag&sort=semver)](https://github.com/triggeredcode/jev-compiler/releases/latest)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22C55E.svg)](LICENSE)

**Compile natural-language decision policies into inspectable, measurable TypeSafe Jev programs.**

Jev Compiler turns a decision requirement into a typed graph of Jev questions, probabilities,
thresholds, and deterministic branches. It generates evidence, evaluates alternatives, and freezes
the selected program as a verified deployment artifact with Python and TypeScript runtimes.

![Jev Compiler pipeline](https://raw.githubusercontent.com/triggeredcode/jev-compiler/main/docs/assets/overview.svg)

> **Project status:** `v0.1` is an alpha release for evaluation and development. The typed DSL, safe
> runtime, TypeSafe boundary, local-first teacher layer, dataset synthesis, constrained optimizer,
> held-out evaluation, and immutable artifact pipeline are implemented and tested.

## Why Jev Compiler?

TypeSafe questions return bounded values—`Choice`, `Score`, and `Noul`. Jev Compiler makes the
program around those questions explicit instead of hiding decision logic in one large prompt.

| Capability | What it provides |
| --- | --- |
| Inspectable programs | Typed questions, thresholds, branches, actions, and model selection in YAML/JSON |
| Evidence-driven optimization | Deterministic splits, failure corpora, counterfactual pairs, lineage, and Pareto selection |
| Safe execution | Schema validation and an allowlisted expression interpreter; no Python `eval` or arbitrary code |
| Cost-safe model routing | Ollama, then LM Studio, then OpenRouter's free router; paid models require explicit opt-in |
| Portable deployment | Immutable artifact containing the program, manifest, report, and Python/TypeScript runtimes |
| Reproducible verification | Content digests, replay-only caches, held-out evidence binding, and artifact verification |

Jev Compiler is not a general agent harness, hosted service, or model-training/distillation system.
Its production artifact does not need the development-time teacher model.

## Try it offline in 60 seconds

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node.js 22 for the TypeScript
runtime parity checks.

```bash
git clone https://github.com/triggeredcode/jev-compiler.git
cd jev-compiler
uv sync --extra dev
uv run jevcompiler showcase
```

The showcase uses committed expense-approval fixtures, performs no network calls, evaluates the
expected decision, freezes a deployment artifact, and verifies every file digest. Its output is
written to `.jevcompiler/artifacts/expense-approval/showcase/` and is intentionally ignored by Git.

```text
policy + recorded Jev answers
        -> typed decision graph
        -> deterministic evaluation
        -> frozen artifact
        -> digest verification
```

See the [quickstart](docs/quickstart.md) for validation, live TypeSafe execution, local model setup,
full builds, replay mode, and artifact inspection.

## Core workflow

```bash
# Validate public examples.
uv run jevcompiler validate examples/support-routing/task.yaml --kind task
uv run jevcompiler validate examples/support-routing/program.yaml --kind program

# Run deterministically with recorded TypeSafe answers.
uv run jevcompiler run examples/support-routing/program.yaml \
  examples/support-routing/state.json \
  --answers examples/support-routing/answers.json

# Generate data, compile, optimize, evaluate, and freeze.
uv run jevcompiler build examples/support-routing/task.yaml --budget quick

# Verify and inspect the selected frozen artifact.
uv run jevcompiler artifact verify \
  .jevcompiler/artifacts/support-router/frozen/<candidate-id>
uv run jevcompiler report \
  .jevcompiler/artifacts/support-router/frozen/<candidate-id>
```

Build presets enforce hard ceilings on measured candidates and uncached TypeSafe requests:

- `quick` runs a small structural search.
- `standard` adds semantic rewrites and broader evidence.
- `deep` uses the largest built-in evidence and search budget.

Add `--adaptive-cases N` for one bounded failure-directed improvement round. Development evidence
selects the program; the unchanged test split measures it afterward. Resumed phases are accepted
only when their source hashes and requested budgets still match.

## Model routing and TypeSafe

Automatic teacher selection is local-first:

1. Ollama at `127.0.0.1:11434`
2. LM Studio at `127.0.0.1:1234`
3. OpenRouter's free router when `OPENROUTER_API_KEY` is present
4. A paid OpenRouter model only with a non-free override and `--allow-paid`

Run `uv run jevcompiler doctor` to inspect availability without printing secrets. Teacher selection
and TypeSafe's Jev execution are separate boundaries: export `TYPESAFE_API_KEY` only when making a
live Jev call, and omit `--answers`. Credentials are read from the process environment and must not
be committed.

For deterministic reruns, use `--cache-mode replay_only`. TypeSafe recordings, generated datasets,
programs, metrics, lineage, and failure evidence stay under `.jevcompiler/`, outside version control.

## Deployment artifact

Every frozen artifact is immutable and contains:

- `program.yaml` and equivalent `program.json`
- a digest-bound `manifest.json`
- dependency-free `runtime.py` and `runtime.ts`
- held-out metrics and provenance
- a self-contained HTML inspection report

The TypeScript export exposes `runProgram(program, state, provider)` and `decide(state, provider)`.
Its provider supplies one asynchronous `evaluate(state, questions, { model })` method. Node.js 22
can execute the export directly with type stripping; regular TypeScript toolchains can compile it
for other runtimes.

Read [Architecture](docs/architecture.md) for pipeline boundaries, trust assumptions, and the
artifact contract.

## Repository map

- `src/jevcompiler/specs` — canonical task and restricted decision-program schemas
- `src/jevcompiler/runtime` — safe expression interpreter and graph execution
- `src/jevcompiler/providers` — TypeSafe client and local-first structured teachers
- `src/jevcompiler/dataset` — provenance, labeling, validation, and deterministic splits
- `src/jevcompiler/baseline` — constrained compilation and trace-rich evaluation
- `src/jevcompiler/optimizer` — replay cache, failures, mutations, lineage, and Pareto search
- `src/jevcompiler/freeze` — artifacts, runtimes, verification, and reports
- `examples/` — runnable support-routing and expense-approval examples

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
uv build
uv run python scripts/verify_distribution.py dist
```

Please read [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and the
[changelog](CHANGELOG.md) before contributing or deploying. This project is licensed under the
[MIT License](LICENSE).

## References

- [TypeSafe introduction](https://docs.typesafe.ai/introduction)
- [TypeSafe primitives](https://docs.typesafe.ai/primitives)
- [TypeSafe cookbooks](https://docs.typesafe.ai/cookbooks)
- [TypeSafe models](https://docs.typesafe.ai/models)
