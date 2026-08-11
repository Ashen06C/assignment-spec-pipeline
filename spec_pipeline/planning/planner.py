"""Planning layer — converts formal FeatureSpec documents into structured ImplementationPlans."""

from __future__ import annotations

from collections import deque
from typing import Any

from spec_pipeline.core.config import load_settings
from spec_pipeline.core.models import (
    DecomposedTask,
    EvaluatedRisk,
    FeatureSpec,
    ImplementationPlan,
    TestStrategy,
)
from spec_pipeline.llm import BaseLLMProvider, LLMConfig, get_llm_provider
from spec_pipeline.llm.json_util import parse_llm_json
from spec_pipeline.llm.prompt_templates import (
    PLANNING_SYSTEM_PROMPT,
    build_planning_prompt,
)
from spec_pipeline.planning.risk_analyzer import RiskAnalyzer


def order_tasks_dag(tasks: list[DecomposedTask]) -> list[DecomposedTask]:
    """Topologically sort tasks based on their dependencies (DAG ordering).

    Uses Kahn's algorithm. If a cycle or unknown dependency is detected,
    appends any remaining tasks in their original order to prevent data loss.
    """
    task_map = {t.task_id: t for t in tasks}
    in_degree = {t.task_id: 0 for t in tasks}
    adj: dict[str, list[str]] = {t.task_id: [] for t in tasks}

    for task in tasks:
        for dep in task.dependencies:
            if dep in task_map:
                adj[dep].append(task.task_id)
                in_degree[task.task_id] += 1

    queue: deque[str] = deque([t_id for t_id, deg in in_degree.items() if deg == 0])
    ordered: list[DecomposedTask] = []
    visited: set[str] = set()

    while queue:
        curr_id = queue.popleft()
        ordered.append(task_map[curr_id])
        visited.add(curr_id)

        for neighbor in adj[curr_id]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Append any remaining unvisited tasks (handles cycles gracefully)
    for task in tasks:
        if task.task_id not in visited:
            ordered.append(task)

    return ordered


class Planner:
    """Orchestrates technical planning and risk evaluation for a FeatureSpec."""

    def __init__(
        self,
        llm: BaseLLMProvider | None = None,
        risk_analyzer: RiskAnalyzer | None = None,
    ) -> None:
        if llm is None:
            settings = load_settings()
            llm_config = LLMConfig(
                provider=settings.llm_provider,
                model=settings.llm_model,
                api_key=settings.active_api_key,
            )
            self.llm = get_llm_provider(llm_config)
        else:
            self.llm = llm

        self.risk_analyzer = risk_analyzer or RiskAnalyzer()

    def plan(self, spec: FeatureSpec) -> ImplementationPlan:
        """Convert *spec* into a complete, validated ``ImplementationPlan``."""
        spec_dict = spec.model_dump(mode="json")
        prompt = build_planning_prompt(spec_dict)

        raw_response, _usage = self.llm.generate(
            prompt,
            system_prompt=PLANNING_SYSTEM_PROMPT,
        )

        plan_data = parse_llm_json(raw_response)
        if not isinstance(plan_data, dict):
            raise ValueError("Expected JSON object from LLM planning response")

        # 1. Parse & DAG-order tasks
        raw_tasks = plan_data.get("tasks", [])
        tasks: list[DecomposedTask] = []
        for t in raw_tasks:
            if isinstance(t, dict):
                tasks.append(DecomposedTask(**t))

        if not tasks:
            # Fallback default task if none generated
            tasks = [
                DecomposedTask(
                    task_id="TASK-001",
                    title="Implement core feature",
                    description=f"Implement requirements for {spec.title}",
                    priority="high",
                    target_files=["src/feature.py"],
                )
            ]

        ordered_tasks = order_tasks_dag(tasks)

        # 2. Extract Impacted Files and Modules
        impacted_files = plan_data.get("impacted_files", [])
        if not impacted_files:
            # Infer from tasks if omitted
            inferred_files: set[str] = set()
            for task in ordered_tasks:
                inferred_files.update(task.target_files)
            impacted_files = sorted(inferred_files) if inferred_files else ["src/feature.py"]

        impacted_modules = plan_data.get("impacted_modules", [])
        if not impacted_modules:
            impacted_modules = sorted({f.rsplit("/", 1)[0] for f in impacted_files if "/" in f})

        # 3. Technical summary & ADRs
        technical_summary = plan_data.get(
            "technical_summary",
            f"Technical implementation architecture for '{spec.title}'.",
        )
        architecture_decisions = plan_data.get(
            "architecture_decisions",
            [
                "ADR-001: Implement modular architecture with strict validation",
                "ADR-002: Ensure testability across unit and integration boundaries",
            ],
        )

        # 4. Risk Analysis (merge heuristic rules + LLM output)
        heuristic_risks = self.risk_analyzer.analyze(spec, impacted_files)
        llm_risks_raw = plan_data.get("risks", [])
        combined_risks: list[EvaluatedRisk] = list(heuristic_risks)

        for r in llm_risks_raw:
            if isinstance(r, dict):
                risk_obj = EvaluatedRisk(**r)
                # Deduplicate if similar description exists
                if not any(
                    r_exist.description.lower() == risk_obj.description.lower()
                    for r_exist in combined_risks
                ):
                    combined_risks.append(risk_obj)

        # 5. Test Strategy
        test_strat_raw: dict[str, Any] = plan_data.get("test_strategy", {})
        ac_map = test_strat_raw.get("acceptance_test_mapping", {})
        # Ensure all spec ACs are represented in mapping
        for ac in spec.acceptance_criteria:
            if ac.criterion_id not in ac_map:
                ac_map[ac.criterion_id] = f"Validate criterion: {ac.title}"

        test_strategy = TestStrategy(
            unit_test_focus=test_strat_raw.get(
                "unit_test_focus",
                ["Domain model validation", "Business logic invariants"],
            ),
            integration_test_focus=test_strat_raw.get(
                "integration_test_focus",
                ["API endpoints contract verification", "Persistence integration"],
            ),
            acceptance_test_mapping=ac_map,
        )

        return ImplementationPlan(
            spec_id=spec.spec_id,
            technical_summary=technical_summary,
            architecture_decisions=architecture_decisions,
            tasks=ordered_tasks,
            impacted_modules=impacted_modules,
            impacted_files=impacted_files,
            risks=combined_risks,
            test_strategy=test_strategy,
        )
