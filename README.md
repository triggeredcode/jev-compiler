# Jev Compiler

Jev Compiler turns a natural-language decision policy into an inspectable program made from
TypeSafe Jev questions, probabilities, thresholds, and deterministic branches.

The project is an **automatic compiler for Jev decision workflows**. It is not an agent harness,
a generic prompt optimizer, a hosted service, or a model-training/distillation system.

> Status: the foundation, typed DSL, safe runtime, TypeSafe boundary, structured teacher layer,
> provenance-aware dataset synthesis, constrained baseline compiler/evaluator, and the measurable
> optimization core are implemented. Failure-directed training evidence and paired counterfactual
> stability are included. The compiler can produce verified, immutable deployment artifacts with a
> self-contained inspection report.

## Why this shape

TypeSafe questions return bounded, typed values: Choice, Score, and Noul. Questions that share a
state should normally be batched into one request and combined in deterministic code. Jev Compiler
makes that surrounding program explicit, testable, and optimizable.

```text
decision requirement -> teacher-generated cases -> Jev graph -> evaluate -> optimize -> freeze
```

The production artifact does not need its development-time teacher model.

## Quick start

```bash
uv sync --extra dev
uv run jevcompiler validate examples/support-routing/task.yaml --kind task
uv run jevcompiler validate examples/support-routing/program.yaml --kind program
uv run jevcompiler run examples/support-routing/program.yaml \
  examples/support-routing/state.json \
  --answers examples/support-routing/answers.json
uv run jevcompiler build examples/support-routing/task.yaml --budget quick
uv run jevcompiler build examples/support-routing/task.yaml \
  --budget standard --adaptive-cases 4
uv run jevcompiler artifact verify \
  .jevcompiler/artifacts/support-router/frozen/<candidate-id>
uv run jevcompiler report \
  .jevcompiler/artifacts/support-router/frozen/<candidate-id>
uv run pytest
```

`build` runs dataset generation, baseline compilation, optimization, and artifact freezing in
dependency order. It validates compatible phase outputs before resuming. Use `--budget quick` for a
small structural search, `standard` for semantic rewrites and a broader search, or `deep` for the
largest built-in evidence and search budget. Every preset enforces hard ceilings for measured
candidates and uncached TypeSafe requests.

`--adaptive-cases N` adds one bounded improvement round after the initial optimization. The selected
program is evaluated on training data, failures drive `N` new train-only cases, the baseline is
recompiled, and selection is repeated against the unchanged development split before the unchanged
test split is measured. Candidate and live-call ceilings are shared across both rounds. Validated
adaptive outputs are resumed only when their source corpus, source candidate, requested case count,
and resulting corpus hash still match.

Each phase is also available independently:

```bash
uv run jevcompiler dataset build examples/support-routing/task.yaml --normal 8 --boundary 4
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

After an optimization run, generate new training evidence from its selected failure corpus:

```bash
uv run jevcompiler dataset adapt \
  examples/support-routing/task.yaml \
  .jevcompiler/artifacts/support-router/dataset \
  .jevcompiler/artifacts/support-router/optimization/selected-failures/failures.json \
  --output .jevcompiler/artifacts/support-router/adaptive-dataset
```

Adaptive generation accepts failures from the training split only. Every new case cites its source
failure, duplicate states are rejected, and the existing development and test splits remain
unchanged. Use the resulting dataset in the next baseline and optimization cycle.

For a live Jev call, export `TYPESAFE_API_KEY` and omit `--answers`. Supply every credential through
the process environment and never commit local key files or generated provider recordings.

## Teacher selection policy

Automatic selection is intentionally cost-safe:

1. Ollama on `127.0.0.1:11434`
2. LM Studio on `127.0.0.1:1234`
3. OpenRouter's free router when `OPENROUTER_API_KEY` is configured
4. A paid OpenRouter model only after explicit opt-in

Run `jevcompiler doctor` to see availability without printing secrets. The dataset and baseline
commands use this order automatically. A paid model requires both a non-free model override and
`--allow-paid`; it is never selected implicitly. Provider selection for the teacher and TypeSafe's
Jev execution are separate concerns.

All generated datasets, programs, metrics, lineage, and failure evidence live under
`.jevcompiler/artifacts/<task>/`. TypeSafe recordings live under `.jevcompiler/cache/`, and the
entire workspace is excluded from version control. Use `--cache-mode replay_only` for a fully
offline rerun.

Add `--semantic --task <task.yaml>` to request bounded question rewrites through the same local-first
teacher policy. A rewrite cannot add actions or arbitrary code.

Optimization uses the development split for selection, then measures the fixed baseline and selected
program on the untouched test split. Frozen manifests bind those held-out results to the exact test
cases by digest. The self-contained report shows baseline/final comparisons, accuracy by generation,
paired counterfactual stability, the Pareto trade-off, candidate lineage, and failure evidence.

## Repository map

- `src/jevcompiler/specs`: canonical TaskSpec and restricted DecisionProgram DSL
- `src/jevcompiler/runtime`: safe expression interpreter and graph execution
- `src/jevcompiler/providers`: TypeSafe client and local-first structured teacher adapters
- `src/jevcompiler/dataset`: provenance, labeling, validation, and deterministic splits
- `src/jevcompiler/baseline`: constrained compilation and trace-rich evaluation
- `src/jevcompiler/optimizer`: cache/replay, failure evidence, mutations, lineage, and Pareto search
- `src/jevcompiler/freeze`: immutable artifact manifests, integrity verification, and static reports
- `src/jevcompiler/security.py`: log-safe secret redaction
- `examples/support-routing`: runnable offline example

## Security and terms

Candidate programs are declarative data. They cannot import modules, execute Python, access the
filesystem, or make arbitrary network calls. The expression engine does not use `eval`.

Jev Compiler optimizes application workflows. It does not train or distill a model from Jev
outputs. Users remain responsible for complying with provider terms. See [SECURITY.md](SECURITY.md).

## References

- [TypeSafe introduction](https://docs.typesafe.ai/introduction)
- [TypeSafe primitives](https://docs.typesafe.ai/primitives)
- [TypeSafe cookbooks](https://docs.typesafe.ai/cookbooks)
- [TypeSafe models](https://docs.typesafe.ai/models)

Licensed under the MIT License.
