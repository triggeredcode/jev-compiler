<p align="center">
  <img src="https://raw.githubusercontent.com/triggeredcode/jev-compiler/main/docs/assets/mark.svg" width="96" alt="Jev Compiler mark">
</p>

<h1 align="center">Jev Compiler</h1>

<p align="center">
  <strong>Turn written decision rules into small programs you can test, inspect, and run anywhere.</strong>
  <br>
  Describe the decision. Give a few examples. Let Jev Compiler build the workflow and show its work.
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
  <a href="#what-is-jev">What is Jev?</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#local-first-model-routing">Model routing</a> ·
  <a href="#container-quickstart">Containers</a> ·
  <a href="#deployment-artifact">Deployment</a> ·
  <a href="#documentation">Documentation</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/triggeredcode/jev-compiler/main/docs/assets/overview.svg" width="100%" alt="Jev Compiler turns a decision policy into evidence, a typed Jev graph, and a verified deployment artifact">
</p>

<p align="center">
  <sub>From a policy people can read to a decision program software can trust</sub>
</p>

## Start with the decision, not the machinery

Most teams already know how a decision should be made. It may be written in a handbook, scattered
through support notes, encoded in a long prompt, or simply carried around in someone's head. Jev
Compiler turns that knowledge into an explicit workflow.

You describe the situation, the allowed outcomes, and examples of good decisions. The compiler then
builds a small program, tries it against those examples, improves weak spots, and packages the result.
You can read every question and rule, see why a case took a particular path, and run the finished
program without the model that helped build it.

For example, a support team can say:

> Route billing questions to billing, technical problems to support, and uncertain or urgent cases
> to a person.

Jev Compiler can turn that sentence and a set of example tickets into a workflow that asks focused
questions, applies the team's rules, chooses an action, and leaves a trace that explains the result.
The same pattern works for expense approvals, security triage, document review, lead routing, agent
quality checks, and other decisions that sit between rigid `if` statements and an opaque prompt.

## What you get

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>Logic you can read</h3>
      The questions, rules, thresholds, and outcomes stay visible instead of disappearing inside a prompt.
    </td>
    <td width="33%" valign="top">
      <h3>Changes you can test</h3>
      Compare versions on examples and difficult cases before changing how real decisions are made.
    </td>
    <td width="33%" valign="top">
      <h3>A result you can ship</h3>
      Freeze the chosen workflow with its test results, history, and ready-to-run Python and TypeScript runtimes.
    </td>
  </tr>
</table>

## What is Jev?

[Jev](https://docs.typesafe.ai/introduction) is TypeSafe AI's first System One model. Instead of
writing a paragraph for a person to read, it answers focused questions in shapes that software can
use directly: choose one option, score something on a scale, or estimate whether a statement is true.
It also returns probabilities, so a workflow can act when the answer is clear and ask for human review
when it is not.

Jev Compiler is the layer around those judgments. It helps turn a larger policy into focused
questions plus ordinary rules, tests the complete workflow, and produces a portable decision program.
Jev is used for the uncertain parts; code remains in control of the final behavior.

### Learn the ideas behind the project

| Resource | Why it is useful |
| --- | --- |
| [TypeSafe AI](https://typesafe.ai/) | The company and the broader idea of machine-native decision models |
| [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) | The plain-language announcement, motivation, demonstrations, and technical results |
| [Jev introduction](https://docs.typesafe.ai/introduction) | The shortest official explanation of state, typed questions, answers, and confidence |
| [Choice, Score, and Noul](https://docs.typesafe.ai/primitives) | The three focused question types used to build workflows |
| [TypeSafe cookbooks](https://docs.typesafe.ai/cookbooks) | Practical examples and patterns for real applications |
| [Available models](https://docs.typesafe.ai/models) | Current Jev model options and their intended use |
| [Workflow evaluations](https://evals.typesafe.ai/) | Interactive examples showing policies decomposed into questions and code |

Jev Compiler is an independent open-source project. It is not a general agent harness, hosted
service, or model-training/distillation system.

## Quickstart

### Do I need an API key?

Not for the offline showcase, recorded replay, artifact inspection, or verification. Those paths run
without credentials or network access.

A key is required only when Jev Compiler makes a live call to Jev. There is no separate Jev Compiler
key: use a **TypeSafe API key** from the [TypeSafe dashboard](https://console.typesafe.ai/), expose it
to the process as `TYPESAFE_API_KEY`, and keep it out of tracked files. The
[official TypeSafe quickstart](https://docs.typesafe.ai/introduction/quickstart) explains the same
setup for direct API and SDK use.

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

### Container quickstart

Prefer an isolated toolchain? The hardened image runs as a non-root user and keeps generated output
in a Docker volume:

```bash
docker compose build compiler
docker compose run --rm compiler showcase
```

The default container reaches host-run Ollama and LM Studio. An optional Compose profile can run a
pinned Ollama service alongside the compiler. See the [container guide](docs/containers.md) for
local-model setup, credential injection, storage, and direct image usage.

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
| [Containers](docs/containers.md) | Hardened image, offline showcase, Ollama profile, and credentials |
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
docker compose config --quiet
```

Small, focused pull requests are welcome. New DSL behavior must include model validation,
interpreter coverage, unsafe-input rejection tests, and documentation. New providers must use mocked
HTTP tests and must never log credentials.

Looking for a contained first change? Browse the open
[`good first issue`](https://github.com/triggeredcode/jev-compiler/issues?q=is%3Aissue%20state%3Aopen%20label%3A%22good%20first%20issue%22)
and [`help wanted`](https://github.com/triggeredcode/jev-compiler/issues?q=is%3Aissue%20state%3Aopen%20label%3A%22help%20wanted%22)
queues, then claim one with a short comment.

## Acknowledgements

Jev Compiler builds on the [TypeSafe Jev model](https://docs.typesafe.ai/introduction), including its
[primitives](https://docs.typesafe.ai/primitives), [cookbooks](https://docs.typesafe.ai/cookbooks),
and [model catalog](https://docs.typesafe.ai/models). Jev Compiler is an independent open-source
project focused on compiling decision policies into portable programs.

<p align="center">
  Released under the <a href="LICENSE">MIT License</a>.
</p>
