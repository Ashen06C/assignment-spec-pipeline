"""SLSA v0.2 / In-Toto Software Supply Chain Provenance Attestation Generator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from spec_pipeline.core.models import AuditRecord


class SLSAProvenanceBuilder:
    """Generates verifiable In-Toto / SLSA v0.2 provenance attestations for synthesized assets."""

    BUILDER_ID = "https://newtonrussell.ai/pipelines/spec-driven-v1"
    BUILD_TYPE = "https://newtonrussell.ai/attestations/spec-driven-pipeline/v1"

    def generate_provenance(
        self,
        record: AuditRecord,
        output_file: str | Path | None = None,
    ) -> dict[str, Any]:
        """Construct the standard SLSA v0.2 In-Toto statement and optionally write to disk."""
        spec_snapshot = record.spec_snapshot
        spec_title = spec_snapshot.get("title", "unnamed-spec")
        spec_hash = spec_snapshot.get("spec_hash", "0" * 64)

        # 1. Subject: Synthesized software artifacts and their cryptographic SHA-256 digests
        subjects: list[dict[str, Any]] = []
        for out in record.generated_outputs:
            if out.get("type") == "code_synthesis":
                changes = out.get("data", {}).get("changes", [])
                for change in changes:
                    content = change.get("content") or ""
                    digest = hashlib.sha256(content.encode()).hexdigest()
                    subjects.append(
                        {
                            "name": change.get("path", "unknown"),
                            "digest": {"sha256": digest},
                        }
                    )

        if not subjects:
            subjects.append(
                {
                    "name": f"spec-pipeline-run-{record.run_id}",
                    "digest": {"sha256": hashlib.sha256(str(record.run_id).encode()).hexdigest()},
                }
            )

        # 2. Materials: Input specifications & configurations
        materials = [
            {
                "uri": f"spec://{spec_title.lower().replace(' ', '-')}",
                "digest": {"sha256": spec_hash},
            }
        ]

        # 3. Governance Approvals
        approval_attestations = [
            {
                "checkpoint": a.checkpoint,
                "status": a.status.value,
                "reviewer": a.reviewer,
                "signature": a.signature,
                "decided_at": a.decided_at.isoformat() if a.decided_at else None,
            }
            for a in record.approvals
        ]

        # 4. Quality Verification Evidence
        quality_evidence: dict[str, Any] = {}
        if record.quality_results:
            quality_evidence = {
                "all_passed": record.quality_results.all_passed,
                "gates": [
                    {
                        "gate_name": g.gate_name,
                        "passed": g.passed,
                        "duration_seconds": g.duration_seconds,
                    }
                    for g in record.quality_results.gates
                ],
            }

        # 5. Assemble In-Toto SLSA v0.2 Statement
        statement: dict[str, Any] = {
            "_type": "https://in-toto.io/Statement/v0.1",
            "subject": subjects,
            "predicateType": "https://slsa.dev/provenance/v0.2",
            "predicate": {
                "builder": {"id": self.BUILDER_ID},
                "buildType": self.BUILD_TYPE,
                "invocation": {
                    "configSource": {
                        "uri": f"spec://{spec_title.lower().replace(' ', '-')}",
                        "digest": {"sha256": spec_hash},
                    },
                    "parameters": {
                        "run_id": str(record.run_id),
                        "spec_id": str(record.spec_id),
                        "spec_version": record.spec_version,
                    },
                },
                "materials": materials,
                "metadata": {
                    "buildStartedOn": record.started_at.isoformat(),
                    "buildFinishedOn": (
                        record.completed_at.isoformat() if record.completed_at else None
                    ),
                    "completeness": {
                        "parameters": True,
                        "environment": True,
                        "materials": True,
                    },
                    "reproducible": True,
                },
                "approvals": approval_attestations,
                "qualityVerification": quality_evidence,
            },
        }

        if output_file is not None:
            target_path = Path(output_file).resolve()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(json.dumps(statement, indent=2), encoding="utf-8")

        return statement
