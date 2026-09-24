import asyncio
from datetime import UTC, datetime

import pytest

from jevcompiler.dataset.builder import DatasetBuildError, _case_id, _corpus_hash
from jevcompiler.dataset.models import (
    CaseProvenance,
    DatasetBundle,
    DatasetCase,
    DatasetManifest,
    LabelMetadata,
)
from jevcompiler.optimizer.adaptive import AdaptiveDatasetBuilder
from jevcompiler.optimizer.models import FailureCase, FailureCluster, FailureCorpus
from jevcompiler.providers.teacher import RecordedTeacherProvider
from jevcompiler.specs.task import TaskSpec


def _task() -> TaskSpec:
    return TaskSpec.model_validate(
        {
            "name": "ticket-router",
            "description": "Route tickets",
            "state": {"description": "A ticket with body"},
            "actions": ["billing", "technical", "manual_review"],
            "policy": ["Charges are billing", "Bugs are technical"],
        }
    )


def _case(body: str, action: str) -> DatasetCase:
    now = datetime.now(UTC)
    return DatasetCase(
        id=_case_id({"body": body}),
        state={"body": body},
        expected_action=action,
        bucket="normal",
        summary=body,
        provenance=CaseProvenance(
            source="teacher",
            role="normal_generator",
            provider="recorded",
            requested_model="recorded-model",
            actual_model="recorded-model",
            generated_at=now,
            seed=7,
        ),
        label=LabelMetadata(
            provider="recorded",
            requested_model="recorded-model",
            actual_model="recorded-model",
            labeled_at=now,
            confidence=0.9,
        ),
    )


def _bundle() -> DatasetBundle:
    train = [_case("charged twice", "billing")]
    dev = [_case("app crashes", "technical")]
    test = [_case("unclear request", "manual_review")]
    all_cases = [*train, *dev, *test]
    return DatasetBundle(
        manifest=DatasetManifest(
            task_name="ticket-router",
            seed=7,
            counts={"train": 1, "dev": 1, "test": 1},
            bucket_counts={"normal": 3},
            corpus_hash=_corpus_hash(all_cases),
        ),
        train=train,
        dev=dev,
        test=test,
    )


def _failures(case: DatasetCase) -> FailureCorpus:
    failure = FailureCase(
        case_id=case.id,
        state=case.state,
        bucket=case.bucket,
        expected_action=case.expected_action,
        predicted_action="technical",
        source_provenance=case.provenance,
        label_provenance=case.label,
    )
    return FailureCorpus(
        total_evaluated=1,
        total_failures=1,
        cases=[failure],
        clusters=[
            FailureCluster(
                key="billing->technical",
                description="misroute",
                case_ids=[case.id],
            )
        ],
    )


def test_adaptive_cases_extend_train_without_changing_held_out_splits() -> None:
    dataset = _bundle()
    parent_id = dataset.train[0].id
    state = {"body": "duplicate charge after reinstall"}
    adaptive_id = _case_id(state)
    teacher = RecordedTeacherProvider(
        [
            {
                "cases": [
                    {
                        "state": state,
                        "summary": "near the observed billing misroute",
                        "parent_id": parent_id,
                    }
                ]
            },
            {
                "labels": [
                    {
                        "case_id": adaptive_id,
                        "decision": "billing",
                        "confidence": 0.95,
                        "important_factors": ["duplicate charge"],
                    }
                ]
            },
        ]
    )

    result = asyncio.run(
        AdaptiveDatasetBuilder(teacher).extend(
            _task(), dataset, _failures(dataset.train[0]), count=1, seed=19
        )
    )

    assert result.bundle.dev == dataset.dev
    assert result.bundle.test == dataset.test
    assert result.bundle.train[:1] == dataset.train
    assert result.added_case_ids == [adaptive_id]
    assert result.bundle.train[-1].provenance.role == "adaptive_failure_generator"
    assert result.bundle.manifest.counts == {"train": 2, "dev": 1, "test": 1}
    assert result.bundle.manifest.bucket_counts == {"boundary": 1, "normal": 3}
    assert result.bundle.manifest.corpus_hash != dataset.manifest.corpus_hash


def test_adaptive_generation_rejects_held_out_failure_evidence() -> None:
    dataset = _bundle()
    teacher = RecordedTeacherProvider([{"cases": [{"state": {"body": "unused"}, "summary": "x"}]}])

    with pytest.raises(DatasetBuildError, match="held-out failures"):
        asyncio.run(
            AdaptiveDatasetBuilder(teacher).extend(
                _task(), dataset, _failures(dataset.test[0]), count=1
            )
        )


def test_adaptive_generation_rejects_duplicate_states() -> None:
    dataset = _bundle()
    parent_id = dataset.train[0].id
    teacher = RecordedTeacherProvider(
        [
            {
                "cases": [
                    {
                        "state": dataset.train[0].state,
                        "summary": "copied source",
                        "parent_id": parent_id,
                    }
                ]
            }
        ]
    )

    with pytest.raises(DatasetBuildError, match="duplicate existing evidence"):
        asyncio.run(
            AdaptiveDatasetBuilder(teacher).extend(
                _task(), dataset, _failures(dataset.train[0]), count=1
            )
        )
