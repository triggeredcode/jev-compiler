# Jev Compiler

Jev Compiler turns a natural-language decision policy into an inspectable program made from
TypeSafe Jev questions, probabilities, thresholds, and deterministic branches.

The project is an **automatic compiler for Jev decision workflows**. It is not an agent harness,
a generic prompt optimizer, a hosted service, or a model-training/distillation system.

> Status: the repository foundation, typed DSL, safe expression evaluator, offline runtime,
> TypeSafe HTTP boundary, local-first provider discovery, CLI, and tests are implemented. Dataset
> synthesis and optimization are the next delivery slice.

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
uv run pytest
```

For a live Jev call, export `TYPESAFE_API_KEY` and omit `--answers`. Credentials are read only from
the process environment. The repository intentionally ignores `keys.env` and `.env`.

## Teacher selection policy

Automatic selection is intentionally cost-safe:

1. Ollama on `127.0.0.1:11434`
2. LM Studio on `127.0.0.1:1234`
3. OpenRouter's free router when `OPENROUTER_API_KEY` is configured
4. A paid OpenRouter model only after explicit opt-in

Run `jevcompiler doctor` to see availability without printing secrets. Provider selection for the
teacher and TypeSafe's Jev execution are separate concerns.

## Repository map

- `src/jevcompiler/specs`: canonical TaskSpec and restricted DecisionProgram DSL
- `src/jevcompiler/runtime`: safe expression interpreter and graph execution
- `src/jevcompiler/providers`: Jev provider protocol, TypeSafe client, and teacher discovery
- `src/jevcompiler/security.py`: log-safe secret redaction
- `docs/spec/`: progressive specification from big picture to concrete delivery slices
- `docs/IMPLEMENTATION_PLAN.md`: dependency-aware execution tracker
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
