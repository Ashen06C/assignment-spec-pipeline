"""Immutable audit recorder capturing full pipeline telemetry and cryptographic attestations."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spec_pipeline.core.models import AuditRecord

if TYPE_CHECKING:
    from spec_pipeline.core.models import (
        ApprovalDecision,
        FeatureSpec,
        ImplementationOutput,
        ImplementationPlan,
        QualityGateSuiteResult,
        TestGenerationOutput,
    )
    from spec_pipeline.llm.base import TokenUsage


class AuditLogger:
    """Records every stage interaction into an immutable, verifiable AuditRecord."""

    def create_record(self, spec: FeatureSpec) -> AuditRecord:
        """Initialize an AuditRecord for a new pipeline execution."""
        return AuditRecord(
            spec_id=spec.spec_id,
            spec_version=spec.version,
            spec_snapshot=spec.model_dump(mode="json"),
            started_at=datetime.now(UTC),
        )

    def log_plan(self, record: AuditRecord, plan: ImplementationPlan) -> None:
        """Record technical implementation plan snapshot."""
        record.plan_snapshot = plan.model_dump(mode="json")

    def log_llm_interaction(
        self,
        record: AuditRecord,
        stage: str,
        prompt: str,
        response: str,
        model: str = "",
        usage: TokenUsage | None = None,
    ) -> None:
        """Record an individual LLM prompt and response pair."""
        entry: dict[str, Any] = {
            "stage": stage,
            "timestamp": datetime.now(UTC).isoformat(),
            "model": model,
            "prompt_length": len(prompt),
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "response_length": len(response),
            "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
        }
        if usage:
            entry["token_usage"] = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
        record.llm_interactions.append(entry)

    def log_implementation(
        self, record: AuditRecord, implementation: ImplementationOutput
    ) -> None:
        """Record AI-generated code synthesis output and diffs."""
        record.generated_outputs.append(
            {
                "type": "code_synthesis",
                "data": implementation.model_dump(mode="json"),
            }
        )

    def log_test_generation(
        self, record: AuditRecord, test_output: TestGenerationOutput
    ) -> None:
        """Record automated test generation output and test suites."""
        record.generated_outputs.append(
            {
                "type": "test_generation",
                "data": test_output.model_dump(mode="json"),
            }
        )

    def log_approval(self, record: AuditRecord, decision: ApprovalDecision) -> None:
        """Record a human governance approval or rejection decision."""
        record.approvals.append(decision)

    def log_quality_results(
        self, record: AuditRecord, suite_result: QualityGateSuiteResult
    ) -> None:
        """Record quality gate verification results."""
        record.quality_results = suite_result

    def finalize_record(
        self,
        record: AuditRecord,
        output_dir: str | Path | None = None,
    ) -> AuditRecord:
        """Seal the AuditRecord with completion timestamp and optionally write to disk."""
        if record.completed_at is None:
            record.completed_at = datetime.now(UTC)

        if output_dir is not None:
            target_dir = Path(output_dir).resolve()
            target_dir.mkdir(parents=True, exist_ok=True)
            output_file = target_dir / f"audit_record_{record.run_id}.json"
            data = record.model_dump(mode="json")
            output_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        return record

    @staticmethod
    def compute_integrity_hash(record: AuditRecord) -> str:
        """Compute SHA-256 fingerprint over the serialized audit record."""
        payload = json.dumps(record.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()
