"""Build inspectable failure corpora from evaluation results."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from jevcompiler.baseline.models import EvaluationReport
from jevcompiler.dataset.models import DatasetCase
from jevcompiler.optimizer.models import FailureCase, FailureCluster, FailureCorpus


class FailureCorpusError(ValueError):
    """Evaluation and dataset evidence could not be reconciled."""


def _cluster_key(expected: str, predicted: str | None, error: str | None) -> str:
    if error:
        return "runtime_error"
    return f"{expected}->{predicted or '__missing__'}"


def build_failure_corpus(
    report: EvaluationReport, cases: list[DatasetCase]
) -> FailureCorpus:
    evidence = {case.id: case for case in cases}
    failures: list[FailureCase] = []
    grouped: dict[str, list[str]] = defaultdict(list)

    for result in report.cases:
        case = evidence.get(result.case_id)
        if case is None:
            raise FailureCorpusError(
                f"evaluation references unknown dataset case {result.case_id}"
            )
        if result.correct:
            continue
        key = _cluster_key(
            result.expected_action,
            result.predicted_action,
            result.error,
        )
        grouped[key].append(case.id)
        failures.append(
            FailureCase(
                case_id=case.id,
                state=case.state,
                bucket=case.bucket,
                expected_action=result.expected_action,
                predicted_action=result.predicted_action,
                error=result.error,
                trace=result.trace,
                source_provenance=case.provenance,
                label_provenance=case.label,
            )
        )

    clusters = [
        FailureCluster(
            key=key,
            description=(
                "Provider or runtime error"
                if key == "runtime_error"
                else f"Expected {key.split('->', 1)[0]} but predicted {key.split('->', 1)[1]}"
            ),
            case_ids=sorted(case_ids),
        )
        for key, case_ids in sorted(grouped.items())
    ]
    return FailureCorpus(
        total_evaluated=report.total,
        total_failures=len(failures),
        cases=failures,
        clusters=clusters,
    )


def write_failure_corpus(corpus: FailureCorpus, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "failures.json").write_text(corpus.model_dump_json(indent=2), encoding="utf-8")
    lines = "".join(
        f"{json.dumps(case.model_dump(mode='json'), sort_keys=True)}\n"
        for case in corpus.cases
    )
    (output / "failures.jsonl").write_text(lines, encoding="utf-8")
