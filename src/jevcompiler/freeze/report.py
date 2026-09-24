"""Self-contained static report for a frozen optimization result."""

from __future__ import annotations

from html import escape

from jevcompiler.optimizer.models import CandidateRecord, OptimizationResult


def _metric(candidate: CandidateRecord, name: str) -> str:
    if candidate.metrics is None:
        return "—"
    value = getattr(candidate.metrics, name)
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def _accuracy_chart(result: OptimizationResult) -> str:
    by_generation: dict[int, float] = {}
    for candidate in result.candidates:
        if candidate.metrics is not None:
            by_generation[candidate.generation] = max(
                by_generation.get(candidate.generation, 0.0),
                candidate.metrics.accuracy,
            )
    points = sorted(by_generation.items())
    if not points:
        return "<p>No measured generations.</p>"
    max_generation = max(generation for generation, _ in points)
    coordinates = [
        (
            40 + (generation / max(max_generation, 1)) * 640,
            180 - accuracy * 140,
            generation,
            accuracy,
        )
        for generation, accuracy in points
    ]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in coordinates)
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5">'
        f"<title>generation {generation}: {accuracy:.3f}</title></circle>"
        for x, y, generation, accuracy in coordinates
    )
    return (
        '<svg class="chart" viewBox="0 0 720 210" role="img" '
        'aria-label="Best selection accuracy by generation">'
        '<line x1="40" y1="180" x2="690" y2="180" />'
        '<line x1="40" y1="30" x2="40" y2="180" />'
        f'<polyline points="{polyline}" />{dots}</svg>'
    )


def _pareto_chart(result: OptimizationResult) -> str:
    frontier = [
        candidate
        for candidate in result.candidates
        if candidate.candidate_id in result.pareto_frontier and candidate.metrics is not None
    ]
    if not frontier:
        return "<p>No Pareto frontier measurements.</p>"
    complexities = [
        candidate.metrics.graph_complexity
        for candidate in frontier
        if candidate.metrics is not None
    ]
    max_complexity = max(complexities)

    def render_dot(candidate: CandidateRecord) -> str:
        assert candidate.metrics is not None
        css_class = (
            "selected-dot" if candidate.candidate_id == result.selected_candidate_id else ""
        )
        x = 40 + candidate.metrics.graph_complexity / max(max_complexity, 1) * 640
        y = 180 - candidate.metrics.accuracy * 140
        return (
            f'<circle class="{css_class}" cx="{x:.1f}" cy="{y:.1f}" r="6">'
            f"<title>{escape(candidate.candidate_id)}: accuracy "
            f"{candidate.metrics.accuracy:.3f}, complexity "
            f"{candidate.metrics.graph_complexity}</title></circle>"
        )

    dots = "".join(render_dot(candidate) for candidate in frontier)
    return (
        '<svg class="chart" viewBox="0 0 720 210" role="img" '
        'aria-label="Pareto accuracy versus graph complexity">'
        '<line x1="40" y1="180" x2="690" y2="180" />'
        '<line x1="40" y1="30" x2="40" y2="180" />'
        f"{dots}</svg>"
    )


def render_report(result: OptimizationResult) -> str:
    baseline = next(
        candidate
        for candidate in result.candidates
        if candidate.candidate_id == result.baseline_candidate_id
    )
    selected = next(
        candidate
        for candidate in result.candidates
        if candidate.candidate_id == result.selected_candidate_id
    )
    stages = "".join(
        (
            '<div class="stage">'
            f"<strong>{escape(stage.id)}</strong>"
            f"<span>{escape(stage.type)}</span>"
            "</div>"
        )
        for stage in selected.program.stages
    )
    lineage_rows = "".join(
        (
            "<tr>"
            f"<td><code>{escape(candidate.candidate_id)}</code></td>"
            f"<td>{escape(candidate.parent_id or '—')}</td>"
            f"<td>{escape(candidate.mutation_type)}</td>"
            f"<td>{escape(candidate.status)}</td>"
            f"<td>{_metric(candidate, 'accuracy')}</td>"
            f"<td>{_metric(candidate, 'macro_f1')}</td>"
            f"<td>{_metric(candidate, 'jev_calls')}</td>"
            f"<td>{_metric(candidate, 'graph_complexity')}</td>"
            "</tr>"
        )
        for candidate in result.candidates
    )
    failure_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(cluster.key)}</td>"
            f"<td>{escape(cluster.description)}</td>"
            f"<td>{len(cluster.case_ids)}</td>"
            "</tr>"
        )
        for cluster in result.selected_failures.clusters
    ) or '<tr><td colspan="3">No selected-candidate failures.</td></tr>'
    failure_case_rows = "".join(
        (
            "<tr>"
            f"<td><code>{escape(case.case_id)}</code></td>"
            f"<td>{escape(case.bucket)}</td>"
            f"<td>{escape(case.expected_action)}</td>"
            f"<td>{escape(case.predicted_action or '—')}</td>"
            f"<td>{escape(case.error or '—')}</td>"
            "</tr>"
        )
        for case in result.selected_failures.cases
    ) or '<tr><td colspan="5">No selected-candidate failures.</td></tr>'
    if result.held_out is None:
        held_out_baseline = "—"
        held_out_selected = "—"
        held_out_note = "Held-out test evaluation was unavailable."
    else:
        held_out_baseline = f"{result.held_out.baseline_metrics.accuracy:.3f}"
        held_out_selected = f"{result.held_out.selected_metrics.accuracy:.3f}"
        held_out_note = (
            f"Measured on {result.held_out.selected_evaluation.total} untouched test cases."
        )
    search_note = (
        f"Search stopped after {result.search.evaluated_candidates} candidates "
        f"because of {result.search.stop_reason.replace('_', ' ')}."
        if result.search is not None
        else "Search termination metadata was unavailable."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(selected.program.name)} optimization report</title>
  <style>
    :root {{ color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }}
    body {{ max-width: 1100px; margin: 0 auto; padding: 2rem; line-height: 1.5; }}
    h1, h2 {{ line-height: 1.2; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 1rem;
    }}
    .card, .stage {{ border: 1px solid #8886; border-radius: .6rem; padding: 1rem; }}
    .card strong {{ display: block; font-size: 1.4rem; }}
    .graph {{ display: flex; flex-wrap: wrap; gap: .7rem; align-items: center; }}
    .stage span {{ display: block; opacity: .7; }}
    .stage:not(:last-child)::after {{ content: " →"; margin-left: .7rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; }}
    th, td {{ border-bottom: 1px solid #8885; padding: .6rem; text-align: left; }}
    code {{ font-size: .85em; }}
    .chart {{ width: 100%; max-height: 260px; border: 1px solid #8884; border-radius: .6rem; }}
    .chart line {{ stroke: #888; stroke-width: 1; }}
    .chart polyline {{ fill: none; stroke: #3478f6; stroke-width: 3; }}
    .chart circle {{ fill: #3478f6; }}
    .chart .selected-dot {{ fill: #22a06b; stroke: currentColor; stroke-width: 2; }}
  </style>
</head>
<body>
  <h1>{escape(selected.program.name)} optimization report</h1>
  <p>
    Selected <code>{escape(selected.candidate_id)}</code>
    from {len(result.candidates)} measured candidates.
  </p>
  <p>{escape(search_note)}</p>
  <section class="summary">
    <div class="card"><strong>{_metric(selected, 'accuracy')}</strong>accuracy</div>
    <div class="card"><strong>{_metric(selected, 'macro_f1')}</strong>macro F1</div>
    <div class="card"><strong>{_metric(selected, 'jev_calls')}</strong>Jev calls</div>
    <div class="card"><strong>{result.cache_hits}</strong>cache hits</div>
  </section>
  <h2>Baseline vs selected</h2>
  <table>
    <thead><tr><th>Evidence</th><th>Baseline accuracy</th><th>Selected accuracy</th></tr></thead>
    <tbody>
      <tr>
        <td>Selection split</td>
        <td>{_metric(baseline, 'accuracy')}</td>
        <td>{_metric(selected, 'accuracy')}</td>
      </tr>
      <tr>
        <td>Held-out test</td>
        <td>{held_out_baseline}</td>
        <td>{held_out_selected}</td>
      </tr>
    </tbody>
  </table>
  <p>{escape(held_out_note)}</p>
  <h2>Accuracy by generation</h2>
  {_accuracy_chart(result)}
  <h2>Pareto trade-off</h2>
  <p>Accuracy increases upward; graph complexity increases to the right.</p>
  {_pareto_chart(result)}
  <h2>Decision graph</h2>
  <div class="graph">{stages}</div>
  <h2>Candidate lineage</h2>
  <table>
    <thead><tr>
      <th>Candidate</th><th>Parent</th><th>Mutation</th><th>Status</th>
      <th>Accuracy</th><th>Macro F1</th><th>Calls</th><th>Complexity</th>
    </tr></thead>
    <tbody>{lineage_rows}</tbody>
  </table>
  <h2>Selected failures</h2>
  <table>
    <thead><tr><th>Cluster</th><th>Description</th><th>Cases</th></tr></thead>
    <tbody>{failure_rows}</tbody>
  </table>
  <h2>Failure browser</h2>
  <table>
    <thead><tr>
      <th>Case</th><th>Bucket</th><th>Expected</th><th>Predicted</th><th>Error</th>
    </tr></thead>
    <tbody>{failure_case_rows}</tbody>
  </table>
</body>
</html>
"""
