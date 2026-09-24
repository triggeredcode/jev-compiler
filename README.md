# Jev Compiler

Jev Compiler turns a natural-language decision policy into an inspectable program made from
TypeSafe Jev questions, probabilities, thresholds, and deterministic branches.

The project is an **automatic compiler for Jev decision workflows**. It is not an agent harness,
a generic prompt optimizer, a hosted service, or a model-training/distillation system.

> Status: the foundation, typed DSL, safe runtime, TypeSafe boundary, structured teacher layer,
> provenance-aware dataset synthesis, constrained baseline compiler/evaluator, and the measurable
> optimization core are implemented. Frozen artifacts and showcase reporting are the next slice.

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
uv run jevcompiler dataset build examples/support-routing/task.yaml --normal 8 --boundary 4
uv run jevcompiler baseline build \
  examples/support-routing/task.yaml \
  dist/support-router/dataset
uv run jevcompiler optimize run \
  dist/support-router/baseline/program.yaml \
  dist/support-router/dataset
uv run pytest
```

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

Optimization records TypeSafe responses in `.jevcompiler/jev-cache.sqlite3`, then reuses the exact
same evidence for threshold candidates. Use `--cache-mode replay_only` for a fully offline rerun.
Add `--semantic --task <task.yaml>` to request bounded question rewrites through the same local-first
teacher policy. A rewrite cannot add actions or arbitrary code.

## Repository map

- `src/jevcompiler/specs`: canonical TaskSpec and restricted DecisionProgram DSL
- `src/jevcompiler/runtime`: safe expression interpreter and graph execution
- `src/jevcompiler/providers`: TypeSafe client and local-first structured teacher adapters
- `src/jevcompiler/dataset`: provenance, labeling, validation, and deterministic splits
- `src/jevcompiler/baseline`: constrained compilation and trace-rich evaluation
- `src/jevcompiler/optimizer`: cache/replay, failure evidence, mutations, lineage, and Pareto search
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
- [JevHarness](https://github.com/TianyuCodings/JevHarness)

Licensed under the MIT License.
