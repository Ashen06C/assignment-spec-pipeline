"""Native Python HTTP server and REST API for the Spec Pipeline Web Studio."""

from __future__ import annotations

import json
import mimetypes
import shutil
import tempfile
import urllib.parse
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from spec_pipeline.core.config import load_settings
from spec_pipeline.core.exceptions import SpecValidationError
from spec_pipeline.core.models import (
    ApprovalDecision,
    ApprovalStatus,
    FeatureSpec,
    ImplementationPlan,
)
from spec_pipeline.governance.human_gate import HumanApprovalGate
from spec_pipeline.orchestrator import PipelineOrchestrator, PipelineOrchestratorResult
from spec_pipeline.spec_intake.parser import SpecParser
from spec_pipeline.spec_intake.validator import SpecValidator

STATIC_DIR = Path(__file__).resolve().parent / "static"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class PipelineSession:
    """Represents an active multi-stage governed pipeline execution session."""

    def __init__(self, session_id: str, provider: str = "mock", model: str | None = None) -> None:
        self.session_id = session_id
        self.provider = provider
        self.model = model
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"studio_session_{session_id[:8]}_"))
        self.sandbox_dir = self.work_dir / "sandbox"
        self.artifacts_dir = self.work_dir / "artifacts"
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self.orchestrator = PipelineOrchestrator(
            provider_type=provider,
            model_name=model,
        )
        self.record: Any = None
        self.stage = "INITIALIZED"
        self.spec: FeatureSpec | None = None
        self.plan: ImplementationPlan | None = None
        self.checkpoint_1: ApprovalDecision | None = None
        self.checkpoint_2: ApprovalDecision | None = None
        self.implementation: Any = None
        self.test_generation: Any = None
        self.quality_results: Any = None
        self.provenance: dict[str, Any] | None = None
        self.dashboard_path: Path | None = None
        self.report_path: Path | None = None

    def cleanup(self) -> None:
        """Remove temporary directory."""
        if self.work_dir.is_dir():
            shutil.rmtree(self.work_dir, ignore_errors=True)


# In-memory registry of active sessions
SESSIONS: dict[str, PipelineSession] = {}


class StudioRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request handler serving UI assets and REST API endpoints."""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default verbose logging in tests/console unless needed."""
        return

    # ── Helpers ──────────────────────────────────────────────────────────── #

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        payload = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def _send_error(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self._send_json({"error": message, "status": status}, status=status)

    def _read_json_body(self) -> dict[str, Any]:
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len <= 0:
            return {}
        body = self.rfile.read(content_len).decode("utf-8")
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("Expected JSON object body")
            return data
        except json.JSONDecodeError as err:
            raise ValueError(f"Malformed JSON body: {err}") from err

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    # ── GET Dispatcher ───────────────────────────────────────────────────── #

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/specs":
            self._handle_get_specs()
        elif path == "/api/models":
            self._handle_get_models()
        elif path.startswith("/api/artifacts/"):
            self._handle_get_artifact(path)
        elif path.startswith("/api/"):
            self._send_error(f"API endpoint not found: {path}", HTTPStatus.NOT_FOUND)
        else:
            self._handle_static_file(path)

    # ── POST Dispatcher ──────────────────────────────────────────────────── #

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        try:
            body = self._read_json_body()
        except ValueError as err:
            self._send_error(str(err), HTTPStatus.BAD_REQUEST)
            return

        try:
            if path == "/api/validate":
                self._handle_validate(body)
            elif path == "/api/plan":
                self._handle_plan(body)
            elif path == "/api/run":
                self._handle_run(body)
            elif path == "/api/pipeline/start":
                self._handle_pipeline_start(body)
            elif path == "/api/pipeline/approve-plan":
                self._handle_pipeline_approve_plan(body)
            elif path == "/api/pipeline/approve-merge":
                self._handle_pipeline_approve_merge(body)
            elif path == "/api/pipeline/reject":
                self._handle_pipeline_reject(body)
            else:
                self._send_error(f"Unknown POST route: {path}", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    # ── Static File Serving ──────────────────────────────────────────────── #

    def _handle_static_file(self, req_path: str) -> None:
        clean_path = req_path.lstrip("/")
        if not clean_path or clean_path == "/":
            clean_path = "index.html"

        file_path = (STATIC_DIR / clean_path).resolve()
        if not str(file_path).startswith(str(STATIC_DIR.resolve())) or not file_path.is_file():
            # Fallback to index.html for SPA routing
            file_path = STATIC_DIR / "index.html"

        if not file_path.is_file():
            self._send_error("Static asset not found", HTTPStatus.NOT_FOUND)
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "application/octet-stream"
        if file_path.suffix == ".css":
            mime_type = "text/css"
        elif file_path.suffix == ".js":
            mime_type = "application/javascript"

        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def _handle_get_artifact(self, path: str) -> None:
        """Serve generated artifact files by session ID and filename."""
        parts = path.strip("/").split("/")
        if len(parts) < 4:
            self._send_error("Invalid artifact request path", HTTPStatus.BAD_REQUEST)
            return

        session_id = parts[2]
        filename = parts[3]
        session = SESSIONS.get(session_id)
        if not session:
            self._send_error(f"Session {session_id} not found", HTTPStatus.NOT_FOUND)
            return

        target_file = (session.artifacts_dir / filename).resolve()
        artifacts_root = str(session.artifacts_dir.resolve())
        if not str(target_file).startswith(artifacts_root) or not target_file.is_file():
            self._send_error(f"Artifact {filename} not found", HTTPStatus.NOT_FOUND)
            return

        mime_type, _ = mimetypes.guess_type(str(target_file))
        mime_type = mime_type or "text/plain"
        content = target_file.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    # ── API Handlers ─────────────────────────────────────────────────────── #

    def _handle_get_specs(self) -> None:
        """List pre-packaged example specifications."""
        specs_dir = REPO_ROOT / "examples" / "specs"
        results = []
        if specs_dir.is_dir():
            parser = SpecParser()
            for p in sorted(specs_dir.iterdir()):
                if p.suffix.lower() in {".md", ".yaml", ".yml", ".json"}:
                    try:
                        spec = parser.parse_file(p)
                        results.append(
                            {
                                "filename": p.name,
                                "title": spec.title,
                                "format": p.suffix.lstrip(".").lower(),
                                "spec_hash": spec.spec_hash,
                                "objective": spec.objective,
                                "content": p.read_text(encoding="utf-8"),
                            }
                        )
                    except Exception:
                        results.append(
                            {
                                "filename": p.name,
                                "title": p.stem.replace("_", " ").title(),
                                "format": p.suffix.lstrip(".").lower(),
                                "spec_hash": "",
                                "objective": "",
                                "content": p.read_text(encoding="utf-8"),
                            }
                        )

        self._send_json({"specs": results})

    def _handle_get_models(self) -> None:
        """Return available providers and configuration status."""
        config = load_settings()
        providers = [
            {
                "id": "mock",
                "name": "Deterministic Mock Engine (Offline / Fast)",
                "default_model": "mock-engine-v1",
                "configured": True,
            },
            {
                "id": "gemini",
                "name": "Google Gemini",
                "default_model": "gemini-2.5-flash",
                "configured": bool(config.gemini_api_key),
            },
            {
                "id": "openai",
                "name": "OpenAI",
                "default_model": "gpt-4o",
                "configured": bool(config.openai_api_key),
            },
        ]
        self._send_json(
            {
                "current_provider": config.llm_provider,
                "current_model": config.llm_model,
                "providers": providers,
            }
        )

    def _handle_validate(self, body: dict[str, Any]) -> None:
        """Validate specification content against 6 mandatory sections."""
        content = str(body.get("content", "")).strip()
        fmt = str(body.get("format", "yaml")).lower()

        if not content:
            self._send_error("Missing 'content' in request body")
            return

        parser = SpecParser()
        validator = SpecValidator()

        try:
            if fmt == "md" or fmt == "markdown":
                spec = parser.parse_markdown(content)
            elif fmt == "json":
                spec = parser.parse_json(content)
            else:
                spec = parser.parse_yaml(content)

            errors = validator.validate(spec)
            valid = len(errors) == 0
            missing_sections = [e for e in errors if "Missing" in e]
            self._send_json(
                {
                    "valid": valid,
                    "spec": spec.model_dump(mode="json"),
                    "errors": errors,
                    "missing_sections": missing_sections,
                    "spec_hash": spec.spec_hash,
                    "section_checklist": {
                        "objective": bool(spec.objective.strip()),
                        "user_stories": len(spec.user_stories) > 0,
                        "business_rules": len(spec.business_rules) > 0,
                        "acceptance_criteria": len(spec.acceptance_criteria) > 0,
                        "non_functional_requirements": len(spec.non_functional_requirements) > 0,
                        "out_of_scope": len(spec.out_of_scope) > 0,
                    },
                }
            )
        except SpecValidationError as exc:
            self._send_json(
                {
                    "valid": False,
                    "spec": None,
                    "errors": exc.missing_sections or [str(exc)],
                    "missing_sections": exc.missing_sections,
                    "spec_hash": "",
                    "section_checklist": {},
                }
            )
        except Exception as exc:
            self._send_json(
                {
                    "valid": False,
                    "spec": None,
                    "errors": [str(exc)],
                    "missing_sections": [],
                    "spec_hash": "",
                    "section_checklist": {},
                }
            )

    def _handle_plan(self, body: dict[str, Any]) -> None:
        """Generate Technical Implementation Plan and Risk Analysis."""
        content = str(body.get("content", "")).strip()
        fmt = str(body.get("format", "yaml")).lower()
        provider = str(body.get("provider", "mock"))
        model = body.get("model")

        if not content:
            self._send_error("Missing 'content' in request body")
            return

        orchestrator = PipelineOrchestrator(provider_type=provider, model_name=model)
        spec, plan, _record = orchestrator.stage_plan(content, fmt=fmt)

        self._send_json(
            {
                "spec": spec.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
            }
        )

    def _handle_run(self, body: dict[str, Any]) -> None:
        """Execute complete 7-stage pipeline in one continuous run."""
        content = str(body.get("content", "")).strip()
        fmt = str(body.get("format", "yaml")).lower()
        provider = str(body.get("provider", "mock"))
        model = body.get("model")
        auto_approve = bool(body.get("auto_approve", True))
        reviewer = str(body.get("reviewer", "Web Studio User"))

        if not content:
            self._send_error("Missing 'content' in request body")
            return

        session_id = str(uuid.uuid4())
        session = PipelineSession(session_id=session_id, provider=provider, model=model)
        SESSIONS[session_id] = session

        result: PipelineOrchestratorResult = session.orchestrator.run_pipeline(
            spec_path_or_content=content,
            spec_format=fmt,
            sandbox_dir=session.sandbox_dir,
            artifacts_dir=session.artifacts_dir,
            auto_approve=auto_approve,
            reviewer=reviewer,
        )

        res_dict = {
            "spec": result.spec.model_dump(mode="json"),
            "plan": result.plan.model_dump(mode="json"),
            "checkpoint_1": result.checkpoint_1.model_dump(mode="json"),
            "implementation": result.implementation.model_dump(mode="json"),
            "test_generation": result.test_generation.model_dump(mode="json"),
            "quality_results": result.quality_results.model_dump(mode="json"),
            "checkpoint_2": result.checkpoint_2.model_dump(mode="json"),
            "provenance": result.provenance,
        }

        dashboard_rel_url = f"/api/artifacts/{session_id}/dashboard.html"
        report_rel_url = f"/api/artifacts/{session_id}/audit_report.md"
        prov_rel_url = f"/api/artifacts/{session_id}/provenance.json"

        self._send_json(
            {
                "session_id": session_id,
                "result": res_dict,
                "dashboard_url": dashboard_rel_url,
                "report_url": report_rel_url,
                "provenance_url": prov_rel_url,
            }
        )

    # ── Multi-Stage Governed Pipeline Handlers ───────────────────────────── #

    def _handle_pipeline_start(self, body: dict[str, Any]) -> None:
        """Stage 1 & 2: Start session, intake spec, compute plan & risks."""
        content = str(body.get("content", "")).strip()
        fmt = str(body.get("format", "yaml")).lower()
        provider = str(body.get("provider", "mock"))
        model = body.get("model")

        if not content:
            self._send_error("Missing 'content' in request body")
            return

        session_id = str(uuid.uuid4())
        session = PipelineSession(session_id=session_id, provider=provider, model=model)
        SESSIONS[session_id] = session

        # Stage 1 & 2: Intake & Plan
        session.spec, session.plan, session.record = session.orchestrator.stage_plan(
            content, fmt=fmt
        )
        session.stage = "PLAN_READY"

        self._send_json(
            {
                "session_id": session_id,
                "stage": session.stage,
                "spec": session.spec.model_dump(mode="json"),
                "plan": session.plan.model_dump(mode="json"),
                "requires_approval": "checkpoint_1",
            }
        )

    def _handle_pipeline_approve_plan(self, body: dict[str, Any]) -> None:
        """Checkpoint #1 Approval -> Execute Synthesis, Tests, Quality Gates."""
        raw_session_id = body.get("session_id")
        session_id = str(raw_session_id) if raw_session_id is not None else ""
        reviewer = str(body.get("reviewer") or "Lead Architect")
        comments = str(body.get("comments") or "Pre-implementation design approved.")

        session = SESSIONS.get(session_id)
        if not session or session.stage != "PLAN_READY" or not session.spec or not session.plan:
            msg = "Invalid session or session not ready for plan approval"
            self._send_error(msg, HTTPStatus.BAD_REQUEST)
            return

        # Stage 3: Checkpoint #1 Approval
        gate = HumanApprovalGate()
        session.checkpoint_1 = gate.request_pre_implementation_approval(
            plan=session.plan,
            spec=session.spec,
            auto_approve=True,
            reviewer=reviewer,
            comments=comments,
        )
        session.orchestrator.audit_logger.log_approval(session.record, session.checkpoint_1)

        # Stage 4-6: Implement, Test, and Verify Quality Gates
        impl, tests_out, quality_results = session.orchestrator.stage_implement_and_verify(
            spec=session.spec,
            plan=session.plan,
            sandbox_dir=session.sandbox_dir,
            record=session.record,
        )
        session.implementation = impl
        session.test_generation = tests_out
        session.quality_results = quality_results
        session.stage = "VERIFIED" if quality_results.all_passed else "GATE_FAILED"

        self._send_json(
            {
                "session_id": session_id,
                "stage": session.stage,
                "checkpoint_1": session.checkpoint_1.model_dump(mode="json"),
                "implementation": impl.model_dump(mode="json"),
                "test_generation": tests_out.model_dump(mode="json"),
                "quality_results": quality_results.model_dump(mode="json"),
                "requires_approval": "checkpoint_2" if quality_results.all_passed else None,
            }
        )

    def _handle_pipeline_approve_merge(self, body: dict[str, Any]) -> None:
        """Checkpoint #2 Approval -> Finalize Merge & Generate SLSA Provenance."""
        raw_session_id = body.get("session_id")
        session_id = str(raw_session_id) if raw_session_id is not None else ""
        reviewer = str(body.get("reviewer") or "Release Officer")
        comments = str(body.get("comments") or "Quality verification approved for merge.")

        session = SESSIONS.get(session_id)
        if (
            not session
            or session.stage != "VERIFIED"
            or not session.spec
            or not session.plan
            or not session.implementation
            or not session.test_generation
            or not session.quality_results
        ):
            msg = "Invalid session or session not verified for merge approval"
            self._send_error(msg, HTTPStatus.BAD_REQUEST)
            return

        # Stage 7: Checkpoint #2 & Provenance
        decision_2, prov, _report_md, _dash_html = session.orchestrator.stage_finalize_merge(
            spec=session.spec,
            plan=session.plan,
            implementation=session.implementation,
            quality_suite=session.quality_results,
            record=session.record,
            artifacts_dir=session.artifacts_dir,
            auto_approve=True,
            reviewer=reviewer,
            comments=comments,
        )
        session.checkpoint_2 = decision_2
        session.provenance = prov
        session.stage = "COMPLETED"

        self._send_json(
            {
                "session_id": session_id,
                "stage": session.stage,
                "checkpoint_2": decision_2.model_dump(mode="json"),
                "provenance": prov,
                "dashboard_url": f"/api/artifacts/{session_id}/dashboard.html",
                "report_url": f"/api/artifacts/{session_id}/audit_report.md",
                "provenance_url": f"/api/artifacts/{session_id}/provenance.json",
            }
        )

    def _handle_pipeline_reject(self, body: dict[str, Any]) -> None:
        """Reject pipeline at Checkpoint #1 or Checkpoint #2."""
        raw_session_id = body.get("session_id")
        session_id = str(raw_session_id) if raw_session_id is not None else ""
        checkpoint = str(body.get("checkpoint") or "checkpoint_1")
        reviewer = str(body.get("reviewer") or "Reviewer")
        reason = str(body.get("reason") or "Rejected during review.")

        session = SESSIONS.get(session_id)
        if not session:
            self._send_error("Session not found", HTTPStatus.NOT_FOUND)
            return

        gate = HumanApprovalGate()
        now = datetime.now(UTC)
        payload_hash = (
            session.spec.spec_hash
            if session.spec
            else (session.record.spec_snapshot.get("spec_hash", "") if session.record else "")
        )
        sig = gate.generate_signature(
            checkpoint=checkpoint,
            status=ApprovalStatus.REJECTED.value,
            reviewer=reviewer,
            timestamp_iso=now.isoformat(),
            payload_hash=payload_hash,
        )
        decision = ApprovalDecision(
            checkpoint=checkpoint,
            status=ApprovalStatus.REJECTED,
            reviewer=reviewer,
            comments=reason,
            signature=sig,
            decided_at=now,
        )
        if session.record:
            session.orchestrator.audit_logger.log_approval(session.record, decision)
        session.stage = "REJECTED"

        self._send_json(
            {
                "session_id": session_id,
                "stage": session.stage,
                "decision": decision.model_dump(mode="json"),
            }
        )


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    """Create a threaded HTTP server configured with StudioRequestHandler."""
    server_address = (host, port)
    return ThreadingHTTPServer(server_address, StudioRequestHandler)


def start_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the Web Studio server loop."""
    server = create_server(host, port)
    print(f"Spec Pipeline Web Studio running at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Web Studio server...")
    finally:
        server.server_close()
