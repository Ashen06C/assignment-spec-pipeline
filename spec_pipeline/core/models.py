"""Pydantic domain models for every stage of the spec-driven pipeline.

Model groups
------------
1. **Spec Intake** — ``FeatureSpec`` and its child value objects.
2. **Planning**    — ``ImplementationPlan``, ``DecomposedTask``, ``EvaluatedRisk``.
3. **Implementation** — ``FileChange``, ``ImplementationOutput``.
4. **Test Generation** — ``SynthesizedTest``, ``TestGenerationOutput``.
5. **Quality Gates**   — ``QualityGateResult``, ``QualityGateSuiteResult``.
6. **Governance**      — ``ApprovalStatus``, ``ApprovalDecision``, ``AuditRecord``.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    """Timezone-aware UTC timestamp factory."""
    return datetime.now(UTC)


def _new_uuid() -> UUID:
    return uuid4()


# ──────────────────────────────────────────────────────────────────────────────
# 1.  Spec Intake
# ──────────────────────────────────────────────────────────────────────────────


class UserStory(BaseModel):
    """Single user story expressed in *As a … I want … So that …* form."""

    as_a: str = Field(..., description="The user role (e.g. 'admin', 'shopper')")
    i_want: str = Field(..., description="What the user wants to do")
    so_that: str = Field(..., description="The expected benefit")


class BusinessRule(BaseModel):
    """An invariant the feature must enforce."""

    rule_id: str = Field(..., description="Short identifier, e.g. BR-001")
    description: str


class AcceptanceCriterion(BaseModel):
    """A single testable acceptance criterion."""

    criterion_id: str = Field(..., description="Short identifier, e.g. AC-001")
    title: str = Field(..., description="Short human-readable title")
    given: str = Field(..., description="Precondition")
    when: str = Field(..., description="Action / trigger")
    then: str = Field(..., description="Expected outcome")


class NonFunctionalRequirement(BaseModel):
    """Performance, security, or other cross-cutting constraint."""

    category: str = Field(..., description="e.g. 'performance', 'security', 'accessibility'")
    description: str
    threshold: str | None = Field(
        default=None, description="Quantitative target, e.g. 'p99 < 200ms'"
    )


class FeatureSpec(BaseModel):
    """Root model for a complete feature specification document.

    This is the canonical input to the pipeline.
    """

    spec_id: UUID = Field(default_factory=_new_uuid)
    version: int = Field(default=1, ge=1)
    title: str
    objective: str
    user_stories: list[UserStory] = Field(min_length=1)
    business_rules: list[BusinessRule] = Field(min_length=1)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)
    non_functional_requirements: list[NonFunctionalRequirement] = Field(min_length=1)
    out_of_scope: list[str] = Field(min_length=1)
    created_at: datetime = Field(default_factory=_utcnow)
    spec_hash: str = Field(default="", description="SHA-256 fingerprint of raw spec content")

    # All 6 mandatory sections per the specification standard.
    REQUIRED_SECTIONS: frozenset[str] = frozenset(
        {
            "objective",
            "user_stories",
            "business_rules",
            "acceptance_criteria",
            "non_functional_requirements",
            "out_of_scope",
        }
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2.  Planning Layer
# ──────────────────────────────────────────────────────────────────────────────


class DecomposedTask(BaseModel):
    """A single implementation task derived from the specification."""

    task_id: str = Field(..., description="e.g. TASK-001")
    title: str
    description: str
    priority: str = Field(default="medium", description="low | medium | high | critical")
    estimated_effort: str | None = Field(
        default=None, description="Human-readable estimate, e.g. '2h'"
    )
    dependencies: list[str] = Field(
        default_factory=list, description="IDs of tasks this depends on"
    )
    target_files: list[str] = Field(
        default_factory=list, description="Target file paths affected or created by this task"
    )


class EvaluatedRisk(BaseModel):
    """A risk identified during planning."""

    risk_id: str
    category: str = Field(
        default="general",
        description="Risk category: concurrency | security | blast_radius | performance | general",
    )
    description: str
    likelihood: str = Field(description="low | medium | high")
    impact: str = Field(description="low | medium | high")
    mitigation: str


class TestStrategy(BaseModel):
    """High-level testing strategy produced by the planning layer."""

    __test__ = False

    unit_test_focus: list[str] = Field(default_factory=list)
    integration_test_focus: list[str] = Field(default_factory=list)
    acceptance_test_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Maps acceptance criterion IDs → planned test descriptions",
    )


class ImplementationPlan(BaseModel):
    """Complete output of the planning stage."""

    plan_id: UUID = Field(default_factory=_new_uuid)
    spec_id: UUID
    tasks: list[DecomposedTask] = Field(min_length=1)
    technical_summary: str
    architecture_decisions: list[str] = Field(
        default_factory=list, description="Key architecture decisions / design choices (ADRs)"
    )
    impacted_modules: list[str] = Field(default_factory=list)
    impacted_files: list[str] = Field(default_factory=list)
    risks: list[EvaluatedRisk] = Field(default_factory=list)
    test_strategy: TestStrategy = Field(default_factory=TestStrategy)
    created_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 3.  AI-assisted Implementation
# ──────────────────────────────────────────────────────────────────────────────


class FileChange(BaseModel):
    """Represents a single file creation / modification / deletion."""

    path: str = Field(..., description="Relative path within the sandbox")
    action: str = Field(..., description="create | modify | delete")
    content: str | None = Field(
        default=None, description="Full file content (None for deletions)"
    )
    diff_summary: str | None = Field(
        default=None, description="Human-readable summary of what changed"
    )


class ImplementationOutput(BaseModel):
    """Aggregate result of the AI-assisted implementation stage."""

    plan_id: UUID
    changes: list[FileChange] = Field(default_factory=list)
    change_summary: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 4.  Automated Test Generation
# ──────────────────────────────────────────────────────────────────────────────


class SynthesizedTest(BaseModel):
    """A single generated test case."""

    test_id: str
    test_type: str = Field(..., description="unit | integration | acceptance")
    description: str
    source_criterion_id: str | None = Field(
        default=None,
        description="Links back to an acceptance criterion when applicable",
    )
    file_path: str = Field(..., description="Relative path where the test file lives")
    source_code: str


class TestGenerationOutput(BaseModel):
    """Aggregate output of the test-generation stage."""

    __test__ = False

    plan_id: UUID
    tests: list[SynthesizedTest] = Field(default_factory=list)
    coverage_notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 5.  Quality Gates
# ──────────────────────────────────────────────────────────────────────────────


class QualityGateResult(BaseModel):
    """Result of a single quality-gate check."""

    gate_name: str = Field(..., description="e.g. 'ruff-lint', 'mypy', 'pytest'")
    passed: bool
    details: str = ""
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float | None = None


class QualityGateSuiteResult(BaseModel):
    """Aggregated result of all quality gates for a pipeline run."""

    plan_id: UUID
    gates: list[QualityGateResult] = Field(default_factory=list)
    all_passed: bool = False
    executed_at: datetime = Field(default_factory=_utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# 6.  Governance — Approval & Audit
# ──────────────────────────────────────────────────────────────────────────────


class ApprovalStatus(enum.StrEnum):
    """Status of a human-approval checkpoint."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalDecision(BaseModel):
    """Record of a human approval / rejection at a governance checkpoint."""

    checkpoint: str = Field(..., description="e.g. 'pre-implementation', 'pre-deploy'")
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer: str = ""
    comments: str = ""
    signature: str = Field(
        default="", description="HMAC-SHA256 cryptographic signature token"
    )
    decided_at: datetime | None = None


class AuditRecord(BaseModel):
    """Immutable audit trail entry for a single pipeline run.

    Captures spec versions, prompts, AI outputs, approvals, and gate results
    for full traceability and reproducibility.
    """

    run_id: UUID = Field(default_factory=_new_uuid)
    spec_id: UUID
    spec_version: int
    spec_snapshot: dict[str, Any] = Field(
        default_factory=dict, description="Serialised FeatureSpec at execution time"
    )
    plan_snapshot: dict[str, Any] | None = None
    llm_interactions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Prompt/response pairs logged during AI stages",
    )
    generated_outputs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Serialised implementation and test-generation outputs",
    )
    approvals: list[ApprovalDecision] = Field(default_factory=list)
    quality_results: QualityGateSuiteResult | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
