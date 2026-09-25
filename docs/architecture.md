# Architecture

Jev Compiler is a staged compiler for decision workflows. Each stage emits validated, hashable data
that the next stage consumes.

```text
TaskSpec
  -> generated and curated evidence
  -> constrained baseline program
  -> measured mutations and selection
  -> held-out evaluation
  -> immutable deployment artifact
```

## Compiler stages

1. **Task specification** — defines state fields, available actions, constraints, and objectives.
2. **Evidence synthesis** — produces normal, boundary, semantic-variation, and counterfactual cases
   with provenance and deterministic train/development/test splits.
3. **Baseline compilation** — asks a structured teacher for a restricted `DecisionProgram` and
   repairs only schema-bounded failures.
4. **Evaluation** — runs the same safe interpreter used by deployment, recording traces and
   per-class metrics.
5. **Optimization** — explores threshold and structured graph mutations under candidate and live-call
   ceilings, retaining lineage and Pareto information.
6. **Selection** — uses development evidence to choose a program. The fixed test split is measured
   only after selection.
7. **Freezing** — writes an immutable artifact and binds the exact program, evidence, metrics,
   runtimes, and report with digests.

## Runtime boundary

A decision program is declarative data. It can batch TypeSafe Jev questions, read bounded answers,
evaluate allowlisted expressions, and choose declared actions. It cannot import modules, execute
Python, access the filesystem, spawn processes, or open arbitrary network connections.

The Python and TypeScript runtimes implement the same graph contract. Fixture parity tests exercise
both runtimes. TypeSafe access is supplied through a narrow provider interface rather than embedded
inside the program.

## Teacher boundary

The teacher proposes datasets and restricted programs during compilation. It is not part of the
frozen runtime. Structured responses are schema-validated before use, and semantic rewrites cannot
introduce actions or arbitrary code.

Teacher discovery prefers local Ollama and LM Studio endpoints, then OpenRouter's free router. A paid
OpenRouter model requires an explicit model selection and `--allow-paid`.

## Evidence and selection

Evidence is content-addressed and provenance-aware. Optimization reads training failures and selects
against development data. Test cases cannot affect candidate selection. Frozen manifests bind the
reported held-out metrics to the exact cases by digest.

Semantic-variation pairs measure whether meaning-preserving rephrasing changes a decision.
Counterfactual pairs measure whether the program changes decisions when a relevant fact changes.

## Artifact contract

A frozen artifact includes:

- canonical YAML and JSON forms of the selected program
- manifest, content digests, and source provenance
- Python and dependency-free TypeScript runtimes
- baseline, selected, and held-out metrics
- candidate lineage and failure evidence
- a self-contained HTML inspection report

Artifact directories are write-once. `jevcompiler artifact verify` rejects missing, added, or changed
files covered by the manifest.

## Local workspace

`.jevcompiler/` is the single private, generated workspace. It contains caches, provider recordings,
datasets, candidates, reports, and local planning material. The entire directory is ignored by Git
and excluded from release distributions.
