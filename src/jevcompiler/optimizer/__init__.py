from jevcompiler.optimizer.adaptive import AdaptiveDatasetBuilder, AdaptiveDatasetResult
from jevcompiler.optimizer.adaptive_loop import (
    AdaptiveOptimizationRound,
    run_adaptive_round,
)
from jevcompiler.optimizer.artifacts import write_optimization
from jevcompiler.optimizer.failures import build_failure_corpus, write_failure_corpus
from jevcompiler.optimizer.models import (
    CandidateMetrics,
    CandidateRecord,
    FailureCase,
    FailureCluster,
    FailureCorpus,
    OptimizationResult,
)
from jevcompiler.optimizer.mutations import (
    MutationCandidate,
    MutationError,
    add_choice_early_exit,
    add_question,
    confidence_dimensions,
    merge_choice_questions,
    program_id,
    remove_question,
    rewrite_choice_question,
    set_confidence_threshold,
    split_choice_question,
)
from jevcompiler.optimizer.proposals import ProposalError, propose_question_rewrites
from jevcompiler.optimizer.search import Optimizer, candidate_metrics, pareto_frontier
from jevcompiler.optimizer.stability import counterfactual_stability

__all__ = [
    "AdaptiveDatasetBuilder",
    "AdaptiveDatasetResult",
    "AdaptiveOptimizationRound",
    "CandidateMetrics",
    "CandidateRecord",
    "FailureCase",
    "FailureCluster",
    "FailureCorpus",
    "MutationCandidate",
    "MutationError",
    "OptimizationResult",
    "Optimizer",
    "ProposalError",
    "add_choice_early_exit",
    "add_question",
    "build_failure_corpus",
    "candidate_metrics",
    "counterfactual_stability",
    "confidence_dimensions",
    "merge_choice_questions",
    "pareto_frontier",
    "program_id",
    "propose_question_rewrites",
    "remove_question",
    "run_adaptive_round",
    "rewrite_choice_question",
    "set_confidence_threshold",
    "split_choice_question",
    "write_failure_corpus",
    "write_optimization",
]
