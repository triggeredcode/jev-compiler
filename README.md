<p align="center">
  <img src="https://raw.githubusercontent.com/triggeredcode/jev-compiler/main/docs/assets/mark.svg" width="96" alt="Jev Compiler mark">
</p>

<h1 align="center">Jev Compiler</h1>

<p align="center">
  <strong>Compile decision policies into inspectable, measurable TypeSafe Jev programs.</strong>
  <br>
  Generate evidence, optimize a typed decision graph, and ship a verified artifact—not a hidden prompt.
</p>

<p align="center">
  <a href="https://github.com/triggeredcode/jev-compiler/actions/workflows/ci.yml"><img src="https://github.com/triggeredcode/jev-compiler/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="https://github.com/triggeredcode/jev-compiler/releases/latest"><img src="https://img.shields.io/github/v/release/triggeredcode/jev-compiler?display_name=tag&sort=semver&color=7c3aed" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-2563eb?logo=python&logoColor=white" alt="Python 3.11 or newer">
  <a href="https://github.com/triggeredcode/jev-compiler/attestations"><img src="https://img.shields.io/badge/artifacts-attested-0f766e?logo=github" alt="Attested release artifacts"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-16a34a" alt="MIT License"></a>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#local-first-model-routing">Model routing</a> ·
  <a href="#deployment-artifact">Deployment</a> ·
  <a href="#documentation">Documentation</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/triggeredcode/jev-compiler/main/docs/assets/overview.svg" width="100%" alt="Jev Compiler turns a decision policy into evidence, a typed Jev graph, and a verified deployment artifact">
</p>

<p align="center">
  <sub>Local-first compilation · bounded evaluation · deterministic replay · Python and TypeScript runtimes</sub>
</p>

## Built for decisions that must be understood

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>Inspect the program</h3>
      Questions, thresholds, branches, actions, and model selection live in a typed YAML/JSON graph—not an opaque prompt.
    </td>
    <td width="33%" valign="top">
      <h3>Measure the trade-offs</h3>
      Deterministic splits, failure evidence, counterfactual pairs, lineage, and Pareto selection make changes measurable.
    </td>
    <td width="33%" valign="top">
      <h3>Ship with proof</h3>
      Frozen artifacts bind the exact program, held-out metrics, portable runtimes, provenance, and file digests.
    </td>
  </tr>
</table>

Jev questions produce bounded values—`Choice`, `Score`, and `Noul`. Jev Compiler turns those values
into an explicit decision program that can be reviewed, tested, optimized, replayed, and deployed.
It is a compiler for decision workflows, not a general agent harness, hosted service, or
model-training/distillation system.

## Quickstart

Run the complete showcase without credentials or network access:

```bash
git clone https://github.com/triggeredcode/jev-compiler.git
cd jev-compiler
uv sync --extra dev
uv run jevcompiler showcase
```

```text
action           approve
live_calls       0
artifact_files   10
verified         true
```

The command loads committed expense-approval fixtures, evaluates the expected decision, freezes a
deployment artifact, and verifies every digest. Output stays in the ignored `.jevcompiler/`
workspace. Read the [step-by-step quickstart](docs/quickstart.md) for live TypeSafe execution,
replay mode, and full builds.

> **Release status** — `v0.1` is a public alpha for evaluation and development. The compiler,
> runtimes, artifact verification, and release distributions are tested across Python 3.11–3.13 on
> Linux, macOS, and Windows.

## How it works

| Stage | Input → output | Guarantee |
| --- | --- | --- |
| **1 · Specify** | Policy, state, actions → `TaskSpec` | Strict schema and declared action space |
| **2 · Build evidence** | Normal, boundary, semantic, counterfactual cases → dataset | Provenance and deterministic train/dev/test splits |
| **3 · Compile** | Task + evidence → restricted `DecisionProgram` | Structured output and schema-bounded repair |
| **4 · Optimize** | Baseline + failures → measured candidates | Hard candidate/live-call ceilings and complete lineage |
| **5 · Select** | Development metrics → selected program | Test evidence cannot influence selection |
| **6 · Freeze** | Program + held-out result → deployment artifact | Immutable files, content digests, portable runtimes |

Candidate programs are declarative data. The allowlisted interpreter does not use Python `eval` and
cannot import modules, execute shell commands, read arbitrary files, or open arbitrary sockets. The
development-time teacher is not required by the frozen runtime.

<details>
<summary><strong>Run the full compiler workflow</strong></summary>

```bash
# Validate public examples.
uv run jevcompiler validate examples/support-routing/task.yaml --kind task
uv run jevcompiler validate examples/support-routing/program.yaml --kind program

# Run deterministically with recorded TypeSafe answers.
uv run jevcompiler run examples/support-routing/program.yaml \
  examples/support-routing/state.json \
  --answers examples/support-routing/answers.json

# Generate evidence, compile, optimize, evaluate, and freeze.
uv run jevcompiler build examples/support-routing/task.yaml --budget quick

# Verify and inspect the frozen result.
uv run jevcompiler artifact verify \
  .jevcompiler/artifacts/support-router/frozen/<candidate-id>
uv run jevcompiler report \
  .jevcompiler/artifacts/support-router/frozen/<candidate-id>
```

Build budgets are explicit: `quick` performs a small structural search, `standard` adds semantic
rewrites and broader evidence, and `deep` uses the largest built-in evidence/search limits. Add
`--adaptive-cases N` for one bounded failure-directed improvement round.

</details>

## Local-first model routing

Teacher selection follows a cost-safe order and never selects a paid model implicitly:

```text
Ollama  →  LM Studio  →  OpenRouter free router  →  explicit paid opt-in
 local       local             cloud-free                  --allow-paid
```

```bash
uv run jevcompiler doctor
```

`doctor` checks availability without printing secrets. The teacher and the TypeSafe execution
provider are separate boundaries. Set `TYPESAFE_API_KEY` only for live Jev evaluation; set
`OPENROUTER_API_KEY` only when using OpenRouter. Use `--cache-mode replay_only` to fail closed rather
than make a live request.

## Deployment artifact

Every frozen artifact is write-once and self-contained:

```text
frozen/<candidate-id>/
├── manifest.json          # hashes, provenance, selected candidate
├── program.yaml           # canonical human-readable program
├── program.json           # runtime-ready equivalent
├── runtime.py             # standalone Python runtime
├── runtime.ts             # dependency-free TypeScript runtime
├── metrics.json           # baseline, selected, and held-out results
└── report.html            # portable inspection report
```

The TypeScript export provides `runProgram(program, state, provider)` and `decide(state, provider)`.
Node.js 22 can execute it directly with type stripping, while conventional TypeScript toolchains can
compile it for other targets. Release wheels and source archives are built in GitHub Actions and
published with [artifact attestations](https://github.com/triggeredcode/jev-compiler/attestations).

## Documentation

| Guide | Use it for |
| --- | --- |
| [Quickstart](docs/quickstart.md) | Offline showcase, live TypeSafe calls, build budgets, and replay |
| [Architecture](docs/architecture.md) | Compiler stages, trust boundaries, evidence, and artifact contract |
| [Release guide](docs/releasing.md) | Versioning, local checks, tags, distributions, and attestations |
| [Security policy](SECURITY.md) | Vulnerability reporting, credential handling, and release integrity |
| [Contributing](CONTRIBUTING.md) | Development setup, change guidelines, tests, and pull requests |
| [Changelog](CHANGELOG.md) | User-visible changes by release |

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
uv build
uv run python scripts/verify_distribution.py dist
```

Small, focused pull requests are welcome. New DSL behavior must include model validation,
interpreter coverage, unsafe-input rejection tests, and documentation. New providers must use mocked
HTTP tests and must never log credentials.

## Acknowledgements

Jev Compiler builds on the [TypeSafe Jev model](https://docs.typesafe.ai/introduction), including its
[primitives](https://docs.typesafe.ai/primitives), [cookbooks](https://docs.typesafe.ai/cookbooks),
and [model catalog](https://docs.typesafe.ai/models).

<p align="center">
  Released under the <a href="LICENSE">MIT License</a>.
</p>
