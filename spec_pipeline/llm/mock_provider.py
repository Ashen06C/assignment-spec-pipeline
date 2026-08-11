"""Offline deterministic mock LLM provider for CI and evaluation.

Returns pre-built, structurally valid JSON responses keyed on prompt
content so that the full pipeline can run without network access.
"""

from __future__ import annotations

import json
import re
from typing import Any

from spec_pipeline.llm.base import BaseLLMProvider, TokenUsage


class MockProvider(BaseLLMProvider):
    """Deterministic mock that returns realistic, schema-compliant responses.

    The mock inspects the prompt for stage keywords (``planning``,
    ``implementation`` / ``code``, ``test``) and returns a matching
    JSON payload so downstream stages can proceed.
    """

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: float | None = None,
    ) -> tuple[str, TokenUsage]:
        combined = f"{system_prompt}\n{prompt}".lower()
        response = self._route(combined, prompt)
        text = json.dumps(response, indent=2)

        usage = TokenUsage(
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(text.split()),
            total_tokens=len(prompt.split()) + len(text.split()),
        )
        return text, usage

    # ── routing ─────────────────────────────────────────────────────────── #

    def _route(self, combined: str, raw_prompt: str) -> dict[str, Any]:
        """Pick a mock response based on keywords in the prompt."""
        if (
            "generate the required code" in combined
            or "code changes" in combined
            or "synthesis" in combined
        ):
            return self._implementation_response(raw_prompt)
        if (
            "generate comprehensive test" in combined
            or "test generation" in combined
            or "qa engineer" in combined
            or "test cases" in combined
        ):
            return self._test_generation_response(raw_prompt)
        if (
            "software architect" in combined
            or "produce an implementation plan" in combined
            or "planning" in combined
        ):
            return self._planning_response(raw_prompt)
        if any(kw in combined for kw in ("code", "implement")):
            return self._implementation_response(raw_prompt)
        if "test" in combined:
            return self._test_generation_response(raw_prompt)
        # Fallback — return a generic valid response.
        return self._planning_response(raw_prompt)

    # ── mock payloads ───────────────────────────────────────────────────── #

    @staticmethod
    def _extract_title(prompt: str) -> str:
        """Best-effort title extraction from prompt text."""
        m = re.search(r'"title"\s*:\s*"([^"]+)"', prompt)
        if m:
            return m.group(1)
        m = re.search(r"title:\s*(.+)", prompt, re.IGNORECASE)
        if m:
            return m.group(1).strip().strip('"').strip("'")
        return "Mock Feature"

    def _planning_response(self, prompt: str) -> dict[str, Any]:
        title = self._extract_title(prompt)
        return {
            "technical_summary": (
                f"Implementation plan for '{title}'. "
                "The feature requires a new service module with REST endpoints, "
                "input validation, persistence layer integration, and comprehensive "
                "error handling. The design follows hexagonal architecture principles."
            ),
            "architecture_decisions": [
                "ADR-001: Implement modular service layer with explicit dependency injection",
                "ADR-002: Use Pydantic v2 schemas for strict input validation and serialization",
                "ADR-003: Isolate state management to approved storage interface",
            ],
            "tasks": [
                {
                    "task_id": "TASK-001",
                    "title": "Create core data models",
                    "description": (
                        f"Define Pydantic models for {title} domain objects "
                        "including request/response schemas and database entities."
                    ),
                    "priority": "high",
                    "estimated_effort": "2h",
                    "dependencies": [],
                    "target_files": ["src/models/feature.py"],
                },
                {
                    "task_id": "TASK-002",
                    "title": "Implement service logic",
                    "description": (
                        f"Build the core business logic for {title}, "
                        "including validation, processing, and error handling."
                    ),
                    "priority": "high",
                    "estimated_effort": "3h",
                    "dependencies": ["TASK-001"],
                    "target_files": ["src/services/feature_service.py"],
                },
                {
                    "task_id": "TASK-003",
                    "title": "Add REST API endpoints",
                    "description": (
                        "Expose the service via REST endpoints with proper "
                        "request validation and response serialisation."
                    ),
                    "priority": "medium",
                    "estimated_effort": "2h",
                    "dependencies": ["TASK-002"],
                    "target_files": ["src/api/feature_routes.py"],
                },
            ],
            "impacted_modules": ["src/models", "src/services", "src/api"],
            "impacted_files": [
                "src/models/feature.py",
                "src/services/feature_service.py",
                "src/api/feature_routes.py",
            ],
            "risks": [
                {
                    "risk_id": "RISK-001",
                    "category": "performance",
                    "description": (
                        "Integration with external dependencies may introduce latency."
                    ),
                    "likelihood": "medium",
                    "impact": "medium",
                    "mitigation": (
                        "Add circuit breaker pattern and configurable timeouts."
                    ),
                },
            ],
            "test_strategy": {
                "unit_test_focus": [
                    "Data model validation",
                    "Service logic edge cases",
                    "Input sanitisation",
                ],
                "integration_test_focus": [
                    "API endpoint request/response contracts",
                    "Database persistence round-trip",
                ],
                "acceptance_test_mapping": {
                    "AC-001": "Verify core feature workflow end-to-end",
                    "AC-002": "Verify error handling returns correct status codes",
                    "AC-003": "Verify performance under expected load",
                },
            },
        }

    def _implementation_response(self, prompt: str) -> dict[str, Any]:
        title = self._extract_title(prompt)
        return {
            "changes": [
                {
                    "path": "src/models/feature.py",
                    "action": "create",
                    "content": (
                        '"""Data models for the feature."""\n\n'
                        "from pydantic import BaseModel, Field\n\n\n"
                        "class FeatureRequest(BaseModel):\n"
                        f'    """Request model for {title}."""\n\n'
                        '    name: str = Field(..., description="Feature name")\n'
                        '    enabled: bool = Field(default=True, '
                        'description="Whether the feature is active")\n'
                    ),
                    "diff_summary": f"Created data models for {title}",
                },
                {
                    "path": "src/services/feature_service.py",
                    "action": "create",
                    "content": (
                        '"""Service layer for the feature."""\n\n'
                        "from src.models.feature import FeatureRequest\n\n\n"
                        "class FeatureService:\n"
                        f'    """Business logic for {title}."""\n\n'
                        "    def process(self, request: FeatureRequest)"
                        " -> dict[str, str]:\n"
                        '        """Process a feature request."""\n'
                        "        if not request.name:\n"
                        '            raise ValueError("Name is required")\n'
                        '        return {"status": "processed", '
                        '"name": request.name}\n'
                    ),
                    "diff_summary": f"Created service logic for {title}",
                },
            ],
            "change_summary": (
                f"Generated 2 files for {title}: data models and service layer."
            ),
        }

    def _test_generation_response(self, prompt: str) -> dict[str, Any]:
        title = self._extract_title(prompt)
        return {
            "tests": [
                {
                    "test_id": "TEST-001",
                    "test_type": "unit",
                    "description": f"Unit test: {title} model validation",
                    "source_criterion_id": "AC-001",
                    "file_path": "tests/test_models.py",
                    "source_code": (
                        "import pytest\n"
                        "from src.models.feature import FeatureRequest\n\n\n"
                        "class TestFeatureRequest:\n"
                        "    def test_valid_request(self):\n"
                        '        req = FeatureRequest(name="test")\n'
                        '        assert req.name == "test"\n'
                        "        assert req.enabled is True\n\n"
                        "    def test_name_required(self):\n"
                        "        with pytest.raises(Exception):\n"
                        "            FeatureRequest()\n"
                    ),
                },
                {
                    "test_id": "TEST-002",
                    "test_type": "integration",
                    "description": f"Integration test: {title} service processing",
                    "source_criterion_id": "AC-001",
                    "file_path": "tests/test_service.py",
                    "source_code": (
                        "from src.models.feature import FeatureRequest\n"
                        "from src.services.feature_service import FeatureService\n\n\n"
                        "class TestFeatureService:\n"
                        "    def test_process_valid_request(self):\n"
                        "        service = FeatureService()\n"
                        '        req = FeatureRequest(name="test")\n'
                        "        result = service.process(req)\n"
                        '        assert result["status"] == "processed"\n'
                        '        assert result["name"] == "test"\n\n'
                        "    def test_process_empty_name_raises(self):\n"
                        "        import pytest\n"
                        "        service = FeatureService()\n"
                        '        req = FeatureRequest(name="")\n'
                        "        with pytest.raises(ValueError):\n"
                        "            service.process(req)\n"
                    ),
                },
                {
                    "test_id": "TEST-003",
                    "test_type": "acceptance",
                    "description": f"Acceptance test: {title} end-to-end workflow",
                    "source_criterion_id": "AC-002",
                    "file_path": "tests/test_acceptance.py",
                    "source_code": (
                        "from src.models.feature import FeatureRequest\n"
                        "from src.services.feature_service import FeatureService\n\n\n"
                        "class TestAcceptance:\n"
                        "    def test_full_workflow(self):\n"
                        '        """AC-002: Verify feature processes correctly."""\n'
                        "        service = FeatureService()\n"
                        '        req = FeatureRequest(name="production", '
                        "enabled=True)\n"
                        "        result = service.process(req)\n"
                        '        assert result["status"] == "processed"\n'
                    ),
                },
            ],
            "coverage_notes": (
                f"Generated 3 tests (unit, integration, acceptance) for {title}. "
                "All acceptance criteria AC-001 and AC-002 are covered."
            ),
        }
