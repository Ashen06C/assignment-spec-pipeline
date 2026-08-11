"""Generates executive Markdown reports and responsive standalone HTML visual dashboards."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from spec_pipeline.core.models import AuditRecord

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Spec Pipeline Dashboard: {title}</title>
  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --card-border: #30363d;
      --text: #c9d1d9;
      --text-heading: #f0f6fc;
      --accent: #58a6ff;
      --green: #238636;
      --red: #da3633;
      --yellow: #d29922;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2rem;
    }}
    .container {{ max-width: 1280px; margin: 0 auto; }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 2rem;
    }}
    .header h1 {{ color: var(--text-heading); font-size: 1.8rem; }}
    .header .meta {{ color: #8b949e; font-size: 0.9rem; margin-top: 0.3rem; }}
    .status-pill {{
      padding: 0.5rem 1.2rem;
      border-radius: 9999px;
      font-weight: 700;
      font-size: 0.9rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .status-pill.pass {{
      background: rgba(46, 160, 67, 0.2);
      color: #3fb950;
      border: 1px solid #3fb950;
    }}
    .status-pill.fail {{
      background: rgba(218, 54, 51, 0.2);
      color: #f85149;
      border: 1px solid #f85149;
    }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .metric-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 1.2rem;
    }}
    .metric-card .title {{
      font-size: 0.85rem;
      color: #8b949e;
      text-transform: uppercase;
    }}
    .metric-card .value {{
      font-size: 1.8rem;
      font-weight: 700;
      color: var(--text-heading);
      margin-top: 0.4rem;
    }}
    .section {{ margin-bottom: 2.5rem; }}
    .section h2 {{
      color: var(--text-heading);
      font-size: 1.3rem;
      margin-bottom: 1rem;
      border-bottom: 1px solid #21262d;
      padding-bottom: 0.4rem;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--card-bg);
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid var(--card-border);
      margin-bottom: 1.5rem;
    }}
    th, td {{
      padding: 0.8rem 1rem;
      text-align: left;
      border-bottom: 1px solid var(--card-border);
      font-size: 0.9rem;
    }}
    th {{ background: #1f242c; color: var(--text-heading); font-weight: 600; }}
    tr:hover {{ background: rgba(255, 255, 255, 0.02); }}
    code {{
      font-family: "SFMono-Regular", Consolas, Menlo, monospace;
      background: rgba(110, 118, 129, 0.4);
      padding: 0.2rem 0.4rem;
      border-radius: 4px;
      font-size: 0.85rem;
      color: #e6edf3;
    }}
    .badge {{
      display: inline-block;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
    }}
    .badge-pass {{ background: var(--green); color: #fff; }}
    .badge-fail {{ background: var(--red); color: #fff; }}
    .priority-high, .priority-critical {{ background: rgba(218, 54, 51, 0.3); color: #ff7b72; }}
    .priority-medium {{ background: rgba(210, 153, 34, 0.3); color: #d29922; }}
    .priority-low {{ background: rgba(56, 139, 253, 0.3); color: #58a6ff; }}
    .gates-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 1rem;
    }}
    .gate-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 1.2rem;
    }}
    .gate-card.gate-pass {{ border-left: 4px solid var(--green); }}
    .gate-card.gate-fail {{ border-left: 4px solid var(--red); }}
    .gate-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.4rem;
    }}
    .gate-name {{ font-weight: 700; color: var(--text-heading); font-size: 1rem; }}
    .gate-duration {{ font-size: 0.8rem; color: #8b949e; margin-bottom: 0.4rem; }}
    .gate-details {{ font-size: 0.85rem; color: #c9d1d9; }}
    pre.diff {{
      background: #090c10;
      padding: 1rem;
      border-radius: 6px;
      border: 1px solid var(--card-border);
      overflow-x: auto;
      color: #c9d1d9;
      font-size: 0.85rem;
    }}
    .code-card {{
      margin-bottom: 1rem;
      padding: 1rem;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
    }}
    .code-card h4 {{ margin-bottom: 0.6rem; color: var(--accent); }}
    .sig {{ font-size: 0.75rem; word-break: break-all; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1>{title}</h1>
        <div class="meta">
          Run ID: <code>{run_id}</code> | Spec Hash: <code>{spec_hash_short}...</code>
        </div>
      </div>
      <div class="status-pill {status_class}">{status_text}</div>
    </div>

    <div class="metrics-grid">
      <div class="metric-card">
        <div class="title">Decomposed Tasks</div>
        <div class="value">{task_count}</div>
      </div>
      <div class="metric-card">
        <div class="title">Files Synthesized</div>
        <div class="value">{change_count}</div>
      </div>
      <div class="metric-card">
        <div class="title">Quality Gates</div>
        <div class="value">{passed_gate_count}/{total_gate_count}</div>
      </div>
      <div class="metric-card">
        <div class="title">Evaluated Risks</div>
        <div class="value">{risk_count}</div>
      </div>
    </div>

    <div class="section">
      <h2>Deterministic Quality Verification Evidence</h2>
      <div class="gates-grid">
        {gate_cards}
      </div>
    </div>

    <div class="section">
      <h2>Task DAG & Blast Radius Breakdown</h2>
      <table>
        <thead>
          <tr>
            <th>Task ID</th><th>Title</th><th>Priority</th><th>Effort</th><th>Target Files</th>
          </tr>
        </thead>
        <tbody>
          {task_rows}
        </tbody>
      </table>
    </div>

    <div class="section">
      <h2>Evaluated Risks & Mitigations</h2>
      <table>
        <thead>
          <tr>
            <th>Risk ID</th><th>Category</th><th>Description</th><th>Impact</th><th>Mitigation</th>
          </tr>
        </thead>
        <tbody>
          {risk_rows}
        </tbody>
      </table>
    </div>

    <div class="section">
      <h2>Synthesized Code Modifications & Unified Diffs</h2>
      {diff_cards}
    </div>

    <div class="section">
      <h2>Human Governance Signatures (HMAC-SHA256)</h2>
      <table>
        <thead>
          <tr>
            <th>Checkpoint</th>
            <th>Status</th>
            <th>Reviewer</th>
            <th>Timestamp</th>
            <th>HMAC Signature</th>
          </tr>
        </thead>
        <tbody>
          {approval_rows}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>"""


class AuditReporter:
    """Produces multi-format reports and interactive visual dashboards from AuditRecords."""

    def generate_markdown_report(
        self,
        record: AuditRecord,
        output_file: str | Path | None = None,
    ) -> str:
        """Construct a comprehensive, audit-ready Markdown report."""
        spec = record.spec_snapshot
        plan = record.plan_snapshot or {}
        gates = record.quality_results

        duration_sec = 0.0
        if record.completed_at:
            duration_sec = (record.completed_at - record.started_at).total_seconds()

        status_badge = "✅ PASSED" if (gates and gates.all_passed) else "⚠️ IN-PROGRESS / FAILED"

        lines: list[str] = [
            f"# Spec-Driven Pipeline Audit Report: {spec.get('title', 'Feature')}",
            f"**Run ID**: `{record.run_id}`  ",
            f"**Spec ID**: `{record.spec_id}` (v{record.spec_version})  ",
            f"**Spec SHA-256**: `{spec.get('spec_hash', 'N/A')}`  ",
            f"**Overall Status**: {status_badge}  ",
            f"**Execution Duration**: {duration_sec:.2f}s  ",
            f"**Started At**: `{record.started_at.isoformat()}`  ",
            "\n---\n",
            "## 1. Feature Objective & Requirements",
            f"**Objective**: {spec.get('objective', 'N/A')}\n",
        ]

        # User stories
        stories = spec.get("user_stories", [])
        if stories:
            lines.append("### User Stories")
            for s in stories:
                lines.append(
                    f"- As a **{s.get('as_a')}**, I want **{s.get('i_want')}**, "
                    f"so that **{s.get('so_that')}**."
                )
            lines.append("")

        # 2. Plan & Tasks
        lines.append("## 2. Technical Implementation Plan & Task DAG")
        lines.append(f"**Technical Summary**: {plan.get('technical_summary', 'N/A')}\n")

        adrs = plan.get("architecture_decisions", [])
        if adrs:
            lines.append("### Architecture Decisions (ADRs)")
            for adr in adrs:
                lines.append(f"- {adr}")
            lines.append("")

        tasks = plan.get("tasks", [])
        if tasks:
            lines.extend(
                [
                    "| Task ID | Title | Priority | Effort | Dependencies | Target Files |",
                    "| :--- | :--- | :--- | :--- | :--- | :--- |",
                ]
            )
            for t in tasks:
                deps = ", ".join(t.get("dependencies", [])) or "None"
                files = ", ".join(t.get("target_files", [])) or "—"
                prio = t.get("priority", "").upper()
                lines.append(
                    f"| `{t.get('task_id')}` | {t.get('title')} | {prio} | "
                    f"{t.get('estimated_effort', '—')} | {deps} | `{files}` |"
                )
            lines.append("")

        # 3. Risks
        risks = plan.get("risks", [])
        if risks:
            lines.extend(
                [
                    "### Evaluated Risks & Mitigations",
                    "| Risk ID | Category | Description | Likelihood | Impact | Mitigation |",
                    "| :--- | :--- | :--- | :--- | :--- | :--- |",
                ]
            )
            for r in risks:
                lines.append(
                    f"| `{r.get('risk_id')}` | {r.get('category')} | {r.get('description')} | "
                    f"{r.get('likelihood')} | {r.get('impact')} | {r.get('mitigation')} |"
                )
            lines.append("")

        # 4. Code Synthesis Diffs
        lines.append("## 3. AI-Assisted Code Synthesis & Diffs")
        for out in record.generated_outputs:
            if out.get("type") == "code_synthesis":
                changes = out.get("data", {}).get("changes", [])
                lines.append(f"Total file changes: **{len(changes)}**\n")
                for c in changes:
                    lines.append(f"### File: `{c.get('path')}` ({c.get('action', '').upper()})")
                    if c.get("diff_summary"):
                        lines.append(f"```diff\n{c.get('diff_summary')}\n```\n")

        # 5. Quality Verification Gates
        lines.append("## 4. Deterministic Quality Verification Gates")
        if gates:
            lines.extend(
                [
                    "| Quality Gate | Status | Duration | Details |",
                    "| :--- | :--- | :--- | :--- |",
                ]
            )
            for g in gates.gates:
                status = "✅ PASSED" if g.passed else "❌ FAILED"
                dur = f"{g.duration_seconds:.3f}s" if g.duration_seconds is not None else "—"
                lines.append(f"| `{g.gate_name}` | {status} | {dur} | {g.details} |")
            lines.append("")

        # 6. Governance Approvals & HMAC Signatures
        lines.append("## 5. Human Governance Approvals & HMAC Signatures")
        if record.approvals:
            lines.extend(
                [
                    "| Checkpoint | Status | Reviewer | Timestamp | HMAC-SHA256 Signature |",
                    "| :--- | :--- | :--- | :--- | :--- |",
                ]
            )
            for a in record.approvals:
                decided = a.decided_at.isoformat() if a.decided_at else "—"
                lines.append(
                    f"| `{a.checkpoint}` | **{a.status.value.upper()}** | {a.reviewer} | "
                    f"`{decided}` | `{a.signature[:16]}...{a.signature[-8:]}` |"
                )
            lines.append("")

        report_md = "\n".join(lines)

        if output_file is not None:
            from pathlib import Path

            target_path = Path(output_file).resolve()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(report_md, encoding="utf-8")

        return report_md

    def generate_html_dashboard(
        self,
        record: AuditRecord,
        output_file: str | Path | None = None,
    ) -> str:
        """Construct a responsive, standalone HTML visual dashboard."""
        spec = record.spec_snapshot
        plan = record.plan_snapshot or {}
        gates = record.quality_results

        status_text = (
            "ALL GATES PASSED" if (gates and gates.all_passed) else "GATES FAILED / PENDING"
        )
        status_class = "pass" if (gates and gates.all_passed) else "fail"

        tasks = plan.get("tasks", [])
        risks = plan.get("risks", [])

        # Gather file changes
        changes: list[dict[str, Any]] = []
        for out in record.generated_outputs:
            if out.get("type") == "code_synthesis":
                changes.extend(out.get("data", {}).get("changes", []))

        task_rows = "".join(
            f"<tr><td><code>{t.get('task_id')}</code></td><td>{t.get('title')}</td>"
            f"<td><span class='badge priority-{t.get('priority', 'low')}'>"
            f"{t.get('priority', '').upper()}</span></td>"
            f"<td>{t.get('estimated_effort', '—')}</td>"
            f"<td><code>{', '.join(t.get('target_files', []))}</code></td></tr>"
            for t in tasks
        ) or "<tr><td colspan='5'>No tasks recorded.</td></tr>"

        risk_rows = "".join(
            f"<tr><td><code>{r.get('risk_id')}</code></td>"
            f"<td><span class='badge category'>{r.get('category')}</span></td>"
            f"<td>{r.get('description')}</td>"
            f"<td><span class='badge impact-{r.get('impact', 'low')}'>"
            f"{r.get('impact', '').upper()}</span></td>"
            f"<td>{r.get('mitigation')}</td></tr>"
            for r in risks
        ) or "<tr><td colspan='5'>No risks recorded.</td></tr>"

        diff_cards_list: list[str] = []
        for c in changes:
            summary = escape_html(c.get("diff_summary") or "File modified")
            path = c.get("path", "")
            action = c.get("action", "").upper()
            diff_cards_list.append(
                f"<div class='card code-card'><h4><code>{path}</code> ({action})</h4>"
                f"<pre class='diff'><code>{summary}</code></pre></div>"
            )
        diff_cards = "".join(diff_cards_list) or "<p>No code synthesis modifications recorded.</p>"

        gate_cards = ""
        passed_gates = 0
        total_gates = 0
        if gates:
            total_gates = len(gates.gates)
            passed_gates = len([g for g in gates.gates if g.passed])
            gate_cards = "".join(
                f"<div class='gate-card {'gate-pass' if g.passed else 'gate-fail'}'>"
                f"<div class='gate-header'><span class='gate-name'>{g.gate_name}</span>"
                f"<span class='badge {'badge-pass' if g.passed else 'badge-fail'}'>"
                f"{'PASSED' if g.passed else 'FAILED'}</span></div>"
                f"<div class='gate-duration'>{g.duration_seconds:.3f}s</div>"
                f"<div class='gate-details'>{escape_html(g.details)}</div></div>"
                for g in gates.gates
            )
        if not gate_cards:
            gate_cards = "<p>No quality gate execution recorded.</p>"

        approval_rows_list: list[str] = []
        for a in record.approvals:
            decided = a.decided_at.isoformat() if a.decided_at else "—"
            approval_rows_list.append(
                f"<tr><td><code>{a.checkpoint}</code></td>"
                f"<td><span class='badge badge-pass'>{a.status.value.upper()}</span></td>"
                f"<td>{a.reviewer}</td><td><code>{decided}</code></td>"
                f"<td><code class='sig'>{a.signature}</code></td></tr>"
            )
        approval_rows = (
            "".join(approval_rows_list) or "<tr><td colspan='5'>No approvals recorded.</td></tr>"
        )

        html = HTML_TEMPLATE.format(
            title=escape_html(spec.get("title", "Feature Specification")),
            run_id=record.run_id,
            spec_hash_short=spec.get("spec_hash", "N/A")[:16],
            status_class=status_class,
            status_text=status_text,
            task_count=len(tasks),
            change_count=len(changes),
            passed_gate_count=passed_gates,
            total_gate_count=total_gates,
            risk_count=len(risks),
            gate_cards=gate_cards,
            task_rows=task_rows,
            risk_rows=risk_rows,
            diff_cards=diff_cards,
            approval_rows=approval_rows,
        )

        if output_file is not None:
            from pathlib import Path

            target_path = Path(output_file).resolve()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(html, encoding="utf-8")

        return html


def escape_html(text: str) -> str:
    """Safely escape HTML entities."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
