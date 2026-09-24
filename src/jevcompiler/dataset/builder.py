"""Teacher-backed synthetic dataset construction with deterministic splitting."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import Field, ValidationError, create_model

from jevcompiler.dataset.models import (
    CaseBucket,
    CaseProvenance,
    DatasetBundle,
    DatasetCase,
    DatasetManifest,
    LabelBatch,
    LabelMetadata,
    ScenarioBatch,
    ScenarioDraft,
)
from jevcompiler.providers.teacher import StructuredGeneration, TeacherProvider
from jevcompiler.specs.task import TaskSpec


class DatasetBuildError(RuntimeError):
    """Dataset generation or validation failed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _case_id(state: dict[str, Any]) -> str:
    return f"case_{hashlib.sha256(_canonical_json(state).encode()).hexdigest()[:16]}"


def _corpus_hash(cases: list[DatasetCase]) -> str:
    ordered = sorted((case.model_dump(mode="json") for case in cases), key=lambda item: item["id"])
    return hashlib.sha256(_canonical_json(ordered).encode()).hexdigest()


def _scenario_batch_schema(count: int) -> type[ScenarioBatch]:
    """Create a per-request schema that cannot silently underproduce cases."""
    return cast(
        type[ScenarioBatch],
        create_model(
            f"ScenarioBatch{count}",
            __base__=ScenarioBatch,
            cases=(list[ScenarioDraft], Field(min_length=count, max_length=count)),
        ),
    )


def _split_cases(
    cases: list[DatasetCase], seed: int
) -> tuple[list[DatasetCase], list[DatasetCase], list[DatasetCase]]:
    ranked = sorted(
        cases,
        key=lambda case: hashlib.sha256(f"{seed}:{case.id}".encode()).hexdigest(),
    )
    total = len(ranked)
    if total == 0:
        raise DatasetBuildError("dataset is empty after deduplication")
    if total == 1:
        return ranked, [], []
    if total == 2:
        return ranked[:1], [], ranked[1:]
    dev_count = max(1, round(total * 0.15))
    test_count = max(1, round(total * 0.15))
    while dev_count + test_count >= total:
        if dev_count >= test_count and dev_count > 1:
            dev_count -= 1
        elif test_count > 1:
            test_count -= 1
        else:
            break
    train_count = total - dev_count - test_count
    return (
        ranked[:train_count],
        ranked[train_count : train_count + dev_count],
        ranked[train_count + dev_count :],
    )


class _UnlabeledCase:
    def __init__(
        self,
        *,
        case_id: str,
        state: dict[str, Any],
        bucket: CaseBucket,
        summary: str,
        parent_id: str | None,
        provenance: CaseProvenance,
    ) -> None:
        self.id = case_id
        self.state = state
        self.bucket = bucket
        self.summary = summary
        self.parent_id = parent_id
        self.provenance = provenance


class DatasetBuilder:
    def __init__(self, teacher: TeacherProvider) -> None:
        self.teacher = teacher

    async def build(
        self,
        task: TaskSpec,
        *,
        normal: int = 8,
        boundary: int = 4,
        edge: int = 4,
        counterfactual: int = 4,
        seed: int = 42,
    ) -> DatasetBundle:
        counts = {"normal": normal, "boundary": boundary, "edge": edge}
        generated = await asyncio.gather(
            *(
                self._generate_bucket(task, bucket, count, seed)
                for bucket, count in counts.items()
                if count > 0
            )
        )
        unlabeled = [case for batch in generated for case in batch]
        unlabeled.extend(self._user_examples(task, seed))
        unlabeled = self._deduplicate(unlabeled)

        if counterfactual > 0:
            parents = [case for case in unlabeled if case.bucket in {"normal", "user"}]
            counterfactuals = await self._generate_counterfactuals(
                task, parents, counterfactual, seed
            )
            unlabeled = self._deduplicate([*unlabeled, *counterfactuals])

        labeled = await self._label(task, unlabeled)
        train, dev, test = _split_cases(labeled, seed)
        buckets = Counter(case.bucket for case in labeled)
        manifest = DatasetManifest(
            task_name=task.name,
            seed=seed,
            counts={"train": len(train), "dev": len(dev), "test": len(test)},
            bucket_counts=dict(sorted(buckets.items())),
            corpus_hash=_corpus_hash(labeled),
        )
        return DatasetBundle(manifest=manifest, train=train, dev=dev, test=test)

    async def _generate_bucket(
        self, task: TaskSpec, bucket: str, count: int, seed: int
    ) -> list[_UnlabeledCase]:
        try:
            generation = await self.teacher.structured_generate(
                [
                    {
                        "role": "system",
                        "content": (
                            "You generate evaluation states for a bounded decision policy. Return "
                            "only the requested states. Do not label them or reveal the expected "
                            "action."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Generate exactly {count} distinct {bucket} cases using seed {seed}. "
                            f"TaskSpec:\n{task.model_dump_json(by_alias=True, exclude_none=True)}"
                        ),
                    },
                ],
                _scenario_batch_schema(count),
                temperature=0.4,
            )
        except ValidationError:
            raise DatasetBuildError(
                f"{bucket} generator must return exactly {count} cases"
            ) from None
        return self._materialize_generation(generation, bucket, seed)

    async def _generate_counterfactuals(
        self,
        task: TaskSpec,
        parents: list[_UnlabeledCase],
        count: int,
        seed: int,
    ) -> list[_UnlabeledCase]:
        if not parents:
            return []
        parent_payload = [
            {"id": case.id, "state": case.state, "summary": case.summary}
            for case in parents[: max(count, 1)]
        ]
        try:
            generation = await self.teacher.structured_generate(
                [
                    {
                        "role": "system",
                        "content": (
                            "Generate counterfactual evaluation states. Change exactly one "
                            "policy-relevant factor from a supplied parent and set parent_id to "
                            "that parent's id. Do not label."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Generate exactly {count} counterfactuals using seed {seed}. "
                            f"TaskSpec:\n{task.model_dump_json(by_alias=True, exclude_none=True)}\n"
                            f"Parents:\n{_canonical_json(parent_payload)}"
                        ),
                    },
                ],
                _scenario_batch_schema(count),
                temperature=0.3,
            )
        except ValidationError:
            raise DatasetBuildError(
                f"counterfactual generator must return exactly {count} cases"
            ) from None
        materialized = self._materialize_generation(generation, "counterfactual", seed)
        parent_ids = {case.id for case in parents}
        if any(case.parent_id not in parent_ids for case in materialized):
            raise DatasetBuildError(
                "counterfactual response contains an unknown or missing parent_id"
            )
        return materialized

    @staticmethod
    def _materialize_generation(
        generation: StructuredGeneration[ScenarioBatch], bucket: str, seed: int
    ) -> list[_UnlabeledCase]:
        now = datetime.now(UTC)
        return [
            _UnlabeledCase(
                case_id=_case_id(draft.state),
                state=draft.state,
                bucket=bucket,  # type: ignore[arg-type]
                summary=draft.summary,
                parent_id=draft.parent_id,
                provenance=CaseProvenance(
                    source="teacher",
                    role=f"{bucket}_generator",
                    provider=generation.provider,
                    requested_model=generation.requested_model,
                    actual_model=generation.actual_model,
                    generated_at=now,
                    seed=seed,
                ),
            )
            for draft in generation.value.cases
        ]

    @staticmethod
    def _user_examples(task: TaskSpec, seed: int) -> list[_UnlabeledCase]:
        now = datetime.now(UTC)
        return [
            _UnlabeledCase(
                case_id=_case_id(state),
                state=state,
                bucket="user",
                summary="User-provided example",
                parent_id=None,
                provenance=CaseProvenance(
                    source="user",
                    role="user_input",
                    provider="user",
                    requested_model="none",
                    actual_model="none",
                    generated_at=now,
                    seed=seed,
                ),
            )
            for state in task.examples
        ]

    @staticmethod
    def _deduplicate(cases: list[_UnlabeledCase]) -> list[_UnlabeledCase]:
        unique: dict[str, _UnlabeledCase] = {}
        for case in cases:
            unique.setdefault(case.id, case)
        return list(unique.values())

    async def _label(
        self, task: TaskSpec, cases: list[_UnlabeledCase]
    ) -> list[DatasetCase]:
        if not cases:
            raise DatasetBuildError("no cases were generated")
        payload = [{"case_id": case.id, "state": case.state} for case in cases]
        generation = await self.teacher.structured_generate(
            [
                {
                    "role": "system",
                    "content": (
                        "You are the reference decision-maker. Label every case exactly once "
                        "using only a legal action. Return calibrated confidence and concise "
                        "important factors."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"TaskSpec:\n{task.model_dump_json(by_alias=True, exclude_none=True)}\n"
                        f"Cases:\n{_canonical_json(payload)}"
                    ),
                },
            ],
            LabelBatch,
            temperature=0,
            max_tokens=8192,
        )
        labels = {label.case_id: label for label in generation.value.labels}
        expected_ids = {case.id for case in cases}
        if set(labels) != expected_ids:
            missing = sorted(expected_ids - set(labels))
            extra = sorted(set(labels) - expected_ids)
            raise DatasetBuildError(f"label ids mismatch; missing={missing}, extra={extra}")
        illegal = sorted(
            {label.decision for label in labels.values() if label.decision not in task.actions}
        )
        if illegal:
            raise DatasetBuildError(f"teacher returned illegal actions: {illegal}")
        labeled_at = datetime.now(UTC)
        return [
            DatasetCase(
                id=case.id,
                state=case.state,
                expected_action=labels[case.id].decision,
                bucket=case.bucket,
                summary=case.summary,
                parent_id=case.parent_id,
                provenance=case.provenance,
                label=LabelMetadata(
                    provider=generation.provider,
                    requested_model=generation.requested_model,
                    actual_model=generation.actual_model,
                    labeled_at=labeled_at,
                    confidence=labels[case.id].confidence,
                    important_factors=labels[case.id].important_factors,
                ),
            )
            for case in cases
        ]


def write_dataset(bundle: DatasetBundle, output: Path) -> DatasetManifest:
    output.mkdir(parents=True, exist_ok=True)
    for name, cases in (("train", bundle.train), ("dev", bundle.dev), ("test", bundle.test)):
        content = "".join(f"{case.model_dump_json()}\n" for case in cases)
        (output / f"{name}.jsonl").write_text(content, encoding="utf-8")
    (output / "manifest.json").write_text(
        bundle.manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    return bundle.manifest


def read_dataset(source: Path) -> DatasetBundle:
    try:
        manifest = DatasetManifest.model_validate_json(
            (source / "manifest.json").read_text(encoding="utf-8")
        )
        splits: dict[str, list[DatasetCase]] = {}
        for name in ("train", "dev", "test"):
            lines = (source / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
            splits[name] = [DatasetCase.model_validate_json(line) for line in lines if line]
    except (OSError, ValueError) as exc:
        raise DatasetBuildError(f"unable to read dataset at {source}: {exc}") from None
    bundle = DatasetBundle(manifest=manifest, **splits)  # type: ignore[arg-type]
    actual_hash = _corpus_hash(bundle.all_cases)
    if actual_hash != manifest.corpus_hash:
        raise DatasetBuildError("dataset corpus hash does not match its manifest")
    actual_counts = {"train": len(bundle.train), "dev": len(bundle.dev), "test": len(bundle.test)}
    if actual_counts != manifest.counts:
        raise DatasetBuildError("dataset split counts do not match its manifest")
    return bundle
