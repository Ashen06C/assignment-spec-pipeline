"""Structured prompt templates for each AI-assisted pipeline stage.

Each template defines:
* A ``system_prompt`` — instructions and persona for the model.
* A ``build_prompt(spec_dict)`` function — injects the spec data and
  requests a structured JSON response matching the expected schema.
"""

from __future__ import annotations

import json
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# 1.  Planning Stage
# ──────────────────────────────────────────────────────────────────────────────

PLANNING_SYSTEM_PROMPT = """\
You are a senior software architect. Given a feature specification, produce a \
detailed implementation plan as a JSON object.

Your response MUST be a single valid JSON object (no markdown fences, no \
commentary outside the JSON). Follow the schema exactly."""

PLANNING_JSON_SCHEMA = """\
{
  "technical_summary": "<string – 2-4 sentence design overview>",
  "architecture_decisions": ["<ADR / key design choice 1>", "<ADR 2>"],
  "tasks": [
    {
      "task_id": "TASK-NNN",
      "title": "<string>",
      "description": "<string>",
      "priority": "low | medium | high | critical",
      "estimated_effort": "<string, e.g. '2h'>",
      "dependencies": ["TASK-NNN"],
      "target_files": ["<target file path>"]
    }
  ],
  "impacted_modules": ["<module path>"],
  "impacted_files": ["<file path>"],
  "risks": [
    {
      "risk_id": "RISK-NNN",
      "category": "concurrency | security | blast_radius | performance | general",
      "description": "<string>",
      "likelihood": "low | medium | high",
      "impact": "low | medium | high",
      "mitigation": "<string>"
    }
  ],
  "test_strategy": {
    "unit_test_focus": ["<area>"],
    "integration_test_focus": ["<area>"],
    "acceptance_test_mapping": {
      "AC-NNN": "<planned test description>"
    }
  }
}"""


def build_planning_prompt(spec_dict: dict[str, Any]) -> str:
    """Build the user prompt for the planning stage."""
    return (
        "Analyse the following feature specification and produce an "
        "implementation plan.\n\n"
        "## Feature Specification\n"
        f"```json\n{json.dumps(spec_dict, indent=2)}\n```\n\n"
        "## Required JSON Schema\n"
        f"```json\n{PLANNING_JSON_SCHEMA}\n```\n\n"
        "Respond ONLY with the JSON object."
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2.  Code Synthesis Stage
# ──────────────────────────────────────────────────────────────────────────────

CODE_SYNTHESIS_SYSTEM_PROMPT = """\
You are a senior software engineer. Given a feature specification and an \
implementation plan, generate code changes as a JSON object.

Your response MUST be a single valid JSON object (no markdown fences, no \
commentary). Follow the schema exactly."""

CODE_SYNTHESIS_JSON_SCHEMA = """\
{
  "changes": [
    {
      "path": "<relative file path>",
      "action": "create | modify | delete",
      "content": "<full file content or null for deletions>",
      "diff_summary": "<one-line human-readable summary>"
    }
  ],
  "change_summary": "<string – overall summary of all changes>"
}"""


def build_code_synthesis_prompt(
    spec_dict: dict[str, Any],
    plan_dict: dict[str, Any],
) -> str:
    """Build the user prompt for the code synthesis stage."""
    return (
        "Using the feature specification and implementation plan below, "
        "generate the required code changes.\n\n"
        "## Feature Specification\n"
        f"```json\n{json.dumps(spec_dict, indent=2)}\n```\n\n"
        "## Implementation Plan\n"
        f"```json\n{json.dumps(plan_dict, indent=2)}\n```\n\n"
        "## Required JSON Schema\n"
        f"```json\n{CODE_SYNTHESIS_JSON_SCHEMA}\n```\n\n"
        "Respond ONLY with the JSON object."
    )


# ──────────────────────────────────────────────────────────────────────────────
# 3.  Test Generation Stage
# ──────────────────────────────────────────────────────────────────────────────

TEST_GENERATION_SYSTEM_PROMPT = """\
You are a senior QA engineer. Given a feature specification and the generated \
code changes, produce test cases as a JSON object.

Map each acceptance criterion to at least one test. Include unit, integration, \
and acceptance tests.

Your response MUST be a single valid JSON object (no markdown fences, no \
commentary). Follow the schema exactly."""

TEST_GENERATION_JSON_SCHEMA = """\
{
  "tests": [
    {
      "test_id": "TEST-NNN",
      "test_type": "unit | integration | acceptance",
      "description": "<string>",
      "source_criterion_id": "<AC-NNN or null>",
      "file_path": "<relative test file path>",
      "source_code": "<complete test source code>"
    }
  ],
  "coverage_notes": "<string – summary of test coverage>"
}"""


def build_test_generation_prompt(
    spec_dict: dict[str, Any],
    changes: list[dict[str, Any]],
) -> str:
    """Build the user prompt for the test generation stage."""
    return (
        "Using the feature specification and code changes below, "
        "generate comprehensive test cases.\n\n"
        "## Feature Specification\n"
        f"```json\n{json.dumps(spec_dict, indent=2)}\n```\n\n"
        "## Code Changes\n"
        f"```json\n{json.dumps(changes, indent=2)}\n```\n\n"
        "## Required JSON Schema\n"
        f"```json\n{TEST_GENERATION_JSON_SCHEMA}\n```\n\n"
        "Respond ONLY with the JSON object."
    )
