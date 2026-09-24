"""Generate training evidence from observed optimization failures."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jevcompiler.dataset.builder import (
    DatasetBuilder,
    DatasetBuildError,
    _canonical_json,
    _case_id,
    _corpus_hash,
    _scenario_batch_schema,
    _UnlabeledCase,
)
from jevcompiler.dataset.models import CaseProvenance, DatasetBundle, DatasetManifest
from jevcompiler.optimizer.models import FailureCase, FailureCorpus
from jevcompiler.providers.teacher import TeacherProvider
from jevcompiler.specs.task import TaskSpec


class AdaptiveDatasetResult(BaseModel):
    """A dataset update with an explicit audit trail for newly added cases."""

    model_config = ConfigDict(extra="forbid")

    bundle: DatasetBundle
    added_case_ids: list[str] = Field(min_length=1)
    source_failure_ids: list[str] = Field(min_length=1)


def _rank_failures(corpus: FailureCorpus) -> list[FailureCase]:
    """Rank cases by cluster prevalence, then deterministically by case id."""
    cluster_sizes = {
        case_id: len(cluster.case_ids)
        for cluster in corpus.clusters
        for case_id in cluster.case_ids
    }
    return sorted(
        corpus.cases,
        key=lambda case: (-cluster_sizes.get(case.case_id, 0), case.case_id),
    )


class AdaptiveDatasetBuilder:
    """Append failure-directed teacher cases to training evidence only."""

    def __init__(self, teacher: TeacherProvider) -> None:
        self.teacher = teacher

    async def extend(
        self,
        task: TaskSpec,
        dataset: DatasetBundle,
        failures: FailureCorpus,
        *,
        count: int = 4,
        seed: int = 42,
    ) -> AdaptiveDatasetResult:
        if count < 1:
            raise DatasetBuildError("adaptive case count must be at least one")
        if dataset.manifest.task_name != task.name:
            raise DatasetBuildError(
                f"dataset task {dataset.manifest.task_name!r} does not match task {task.name!r}"
            )

        train_ids = {case.id for case in dataset.train}
        held_out_ids = {case.id for case in [*dataset.dev, *dataset.test]}
        ranked = _rank_failures(failures)
        failure_ids = {case.case_id for case in ranked}
        leaked = sorted(failure_ids & held_out_ids)
        unknown = sorted(failure_ids - train_ids - held_out_ids)
        if leaked:
            raise DatasetBuildError(
                f"adaptive generation cannot consume held-out failures: {leaked}"
            )
        if unknown:
            raise DatasetBuildError(f"adaptive failures are absent from training data: {unknown}")
        if not ranked:
            raise DatasetBuildError("adaptive generation requires at least one training failure")

        source_payload = [
            {
                "case_id": case.case_id,
                "state": case.state,
                "expected_action": case.expected_action,
                "predicted_action": case.predicted_action,
                "error": case.error,
            }
            for case in ranked
        ]
        try:
            generation = await self.teacher.structured_generate(
                [
                    {
                        "role": "system",
                        "content": (
                            "Generate new training states that probe the supplied policy failures. "
                            "Each state must be distinct, must not copy a source state, and must "
                            "set parent_id to the most relevant source case. Do not label the "
                            "states."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Generate exactly {count} failure-directed cases using seed {seed}. "
                            f"TaskSpec:\n{task.model_dump_json(by_alias=True, exclude_none=True)}\n"
                            f"Training failures:\n{_canonical_json(source_payload)}"
                        ),
                    },
                ],
                _scenario_batch_schema(count),
                temperature=0.35,
            )
        except ValidationError:
            raise DatasetBuildError(
                f"adaptive generator must return exactly {count} cases"
            ) from None

        generated_at = datetime.now(UTC)
        unlabeled = [
            _UnlabeledCase(
                case_id=_case_id(draft.state),
                state=draft.state,
                bucket="boundary",
                summary=draft.summary,
                parent_id=draft.parent_id,
                provenance=CaseProvenance(
                    source="teacher",
                    role="adaptive_failure_generator",
                    provider=generation.provider,
                    requested_model=generation.requested_model,
                    actual_model=generation.actual_model,
                    generated_at=generated_at,
                    seed=seed,
                ),
            )
            for draft in generation.value.cases
        ]
        allowed_parents = {case.case_id for case in ranked}
        invalid_parents = sorted(
            {
                case.parent_id or "<missing>"
                for case in unlabeled
                if case.parent_id not in allowed_parents
            }
        )
        if invalid_parents:
            raise DatasetBuildError(
                f"adaptive cases contain unknown or missing parent ids: {invalid_parents}"
            )

        existing_ids = {case.id for case in dataset.all_cases}
        generated_ids = [case.id for case in unlabeled]
        duplicates = sorted(
            {case_id for case_id in generated_ids if generated_ids.count(case_id) > 1}
            | (set(generated_ids) & existing_ids)
        )
        if duplicates:
            raise DatasetBuildError(f"adaptive cases duplicate existing evidence: {duplicates}")

        added = await DatasetBuilder(self.teacher)._label(task, unlabeled)
        train = [*dataset.train, *added]
        all_cases = [*train, *dataset.dev, *dataset.test]
        buckets = Counter(case.bucket for case in all_cases)
        manifest = DatasetManifest(
            task_name=dataset.manifest.task_name,
            seed=dataset.manifest.seed,
            counts={"train": len(train), "dev": len(dataset.dev), "test": len(dataset.test)},
            bucket_counts=dict(sorted(buckets.items())),
            corpus_hash=_corpus_hash(all_cases),
        )
        bundle = DatasetBundle(
            manifest=manifest,
            train=train,
            dev=list(dataset.dev),
            test=list(dataset.test),
        )
        return AdaptiveDatasetResult(
            bundle=bundle,
            added_case_ids=[case.id for case in added],
            source_failure_ids=[case.case_id for case in ranked],
        )
