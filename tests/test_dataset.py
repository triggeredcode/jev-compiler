import asyncio
import json

import pytest

from jevcompiler.dataset.builder import DatasetBuilder, DatasetBuildError, write_dataset
from jevcompiler.providers.teacher import RecordedTeacherProvider
from jevcompiler.specs.task import TaskSpec


def _task() -> TaskSpec:
    return TaskSpec.model_validate(
        {
            "name": "ticket-router",
            "description": "Route tickets",
            "state": {"description": "A ticket with body"},
            "actions": ["billing", "technical", "manual_review"],
            "policy": ["Charges are billing", "Bugs are technical", "Ambiguous is review"],
            "examples": [{"body": "I supplied this example"}],
        }
    )


def test_dataset_generation_deduplication_split_and_provenance(tmp_path) -> None:
    teacher = RecordedTeacherProvider(
        [
            {
                "cases": [
                    {"state": {"body": "charged twice"}, "summary": "billing"},
                    {"state": {"body": "charged twice"}, "summary": "duplicate"},
                    {"state": {"body": "app crashes"}, "summary": "technical"},
                ]
            },
            {"cases": [{"state": {"body": "charge after crash"}, "summary": "boundary"}]},
            {"cases": [{"state": {"body": "empty"}, "summary": "edge"}]},
            {
                "cases": [
                    {
                        "state": {"body": "charge failed because app crashed"},
                        "summary": "single-factor change",
                        "parent_id": "case_316387808690530b",
                    }
                ]
            },
            {
                "labels": [
                    {
                        "case_id": "case_316387808690530b",
                        "decision": "billing",
                        "confidence": 0.9,
                        "important_factors": ["charge"],
                    },
                    {
                        "case_id": "case_8765ffd959d94053",
                        "decision": "technical",
                        "confidence": 0.8,
                        "important_factors": ["crash"],
                    },
                    {
                        "case_id": "case_3cdbe58751da9362",
                        "decision": "manual_review",
                        "confidence": 0.6,
                        "important_factors": ["ambiguous"],
                    },
                    {
                        "case_id": "case_eeea61a1d26b1435",
                        "decision": "manual_review",
                        "confidence": 0.5,
                        "important_factors": ["empty"],
                    },
                    {
                        "case_id": "case_70d80ecddc935059",
                        "decision": "technical",
                        "confidence": 0.85,
                        "important_factors": ["cause"],
                    },
                    {
                        "case_id": "case_901fa6e11546eac9",
                        "decision": "manual_review",
                        "confidence": 0.7,
                        "important_factors": ["user example"],
                    },
                ]
            },
        ]
    )
    builder = DatasetBuilder(teacher)
    bundle = asyncio.run(
        builder.build(_task(), normal=3, boundary=1, edge=1, counterfactual=1, seed=7)
    )

    assert len(bundle.all_cases) == 6
    assert bundle.manifest.counts == {"train": 4, "dev": 1, "test": 1}
    assert bundle.manifest.bucket_counts["user"] == 1
    assert len(bundle.manifest.corpus_hash) == 64
    assert any(case.parent_id for case in bundle.all_cases)
    assert all(case.label.actual_model == "recorded-model" for case in bundle.all_cases)

    write_dataset(bundle, tmp_path)
    assert json.loads((tmp_path / "manifest.json").read_text())["seed"] == 7
    assert len((tmp_path / "train.jsonl").read_text().splitlines()) == 4


def test_dataset_rejects_illegal_teacher_action() -> None:
    teacher = RecordedTeacherProvider(
        [
            {"cases": [{"state": {"body": "hello"}, "summary": "normal"}]},
            {
                "labels": [
                    {
                        "case_id": "case_1da63ae1d1c64f45",
                        "decision": "invented",
                        "confidence": 0.5,
                    }
                ]
            },
        ]
    )
    with pytest.raises(DatasetBuildError, match="illegal actions"):
        asyncio.run(
            DatasetBuilder(teacher).build(
                _task().model_copy(update={"examples": []}),
                normal=1,
                boundary=0,
                edge=0,
                counterfactual=0,
            )
        )


def test_dataset_rejects_an_undersized_generated_batch() -> None:
    teacher = RecordedTeacherProvider(
        [{"cases": [{"state": {"body": "one"}, "summary": "only one"}]}]
    )

    with pytest.raises(DatasetBuildError, match="exactly 2 cases"):
        asyncio.run(
            DatasetBuilder(teacher).build(
                _task().model_copy(update={"examples": []}),
                normal=2,
                boundary=0,
                edge=0,
                counterfactual=0,
            )
        )
