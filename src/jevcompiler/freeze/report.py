"""Self-contained static report for a frozen optimization result."""

from __future__ import annotations

from html import escape

from jevcompiler.optimizer.models import CandidateRecord, OptimizationResult


def _metric(candidate: CandidateRecord, name: str) -> str:
    if candidate.metrics is None:
        return "—"
    value = getattr(candidate.metrics, name)
    return f"{value:.3f}" if isinstance(value, float) else str(value)


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
  </style>
</head>
<body>
  <h1>{escape(selected.program.name)} optimization report</h1>
  <p>
    Selected <code>{escape(selected.candidate_id)}</code>
    from {len(result.candidates)} measured candidates.
  </p>
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
</body>
</html>
"""
