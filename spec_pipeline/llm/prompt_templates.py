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
detailed implementation plan for a Python 3.11+ application as a JSON object.

ARCHITECTURE CONSTRAINTS:
1. Target language MUST be Python. All target files must be under 'src/' \
(e.g., 'src/models/...', 'src/services/...', 'src/controllers/...') with '.py' extensions.
2. Do not target Node.js, JavaScript, or non-Python source files.
3. Your response MUST be a single valid JSON object without markdown fences."""

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
You are a senior software engineer. Given a feature specification and an approved \
implementation plan, generate production Python code changes as a JSON object.

CRITICAL BLAST RADIUS & SANDBOX RULES:
1. You MUST ONLY generate code for the exact file paths in 'impacted_files'.
2. DO NOT create unapproved files (e.g. schemas, scripts, or extra helpers), \
as this triggers a Sandbox Blast Radius Security Violation.
3. Write clean, complete, idiomatic Python code with type annotations.
4. Your response MUST be a single valid JSON object without markdown fences.

STDLIB-ONLY CONSTRAINT (CRITICAL):
5. The sandbox is an ISOLATED Python environment with NO third-party packages installed.
6. You MUST ONLY import from Python's standard library: os, sys, re, json, datetime, \
typing, abc, collections, dataclasses, pathlib, uuid, hashlib, hmac, secrets, \
logging, threading, queue, enum, functools, itertools, contextlib, io, time, math, \
random, struct, copy, traceback, inspect, unittest, and similar stdlib modules.
7. NEVER import from: cryptography, fastapi, flask, django, sqlalchemy, pydantic, \
requests, httpx, boto3, redis, celery, numpy, pandas, jwt, bcrypt, passlib, \
aiohttp, starlette, uvicorn, or ANY other third-party package.
8. If the spec requires encryption, use Python's built-in 'hashlib' and 'hmac' modules.
9. If the spec requires HTTP, use Python's built-in 'http.server' or 'urllib' modules.
10. If the spec requires validation, implement it with plain Python classes and dicts.

SECURITY & TYPING RULES (CRITICAL):
11. NEVER use eval(), exec(), compile(), __import__(), or os.system() in any generated code.
12. ALL functions and methods MUST have complete type annotations including return types. \
Use '-> None' for procedures, '-> str', '-> int', '-> bool', '-> dict', etc. as appropriate. \
NEVER leave a function without a return type annotation.
13. NEVER hardcode real credentials. Use descriptive placeholder names like \
'SECRET_KEY = "your_secret_key_here"' or load from environment variables with os.getenv()."""

CODE_SYNTHESIS_JSON_SCHEMA = """\
{
  "changes": [
    {
      "path": "<relative file path from impacted_files whitelist>",
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
    impacted = plan_dict.get("impacted_files", [])
    files_str = "\n".join(f"- {f}" for f in impacted) if impacted else "- src/feature.py"
    return (
        "Using the feature specification and approved implementation plan below, "
        "generate the required code changes.\n\n"
        "## Whitelisted Impacted Files (You MUST strictly limit changes to ONLY these files):\n"
        f"{files_str}\n\n"
        "## Feature Specification\n"
        f"```json\n{json.dumps(spec_dict, indent=2)}\n```\n\n"
        "## Approved Implementation Plan\n"
        f"```json\n{json.dumps(plan_dict, indent=2)}\n```\n\n"
        "## Required JSON Schema\n"
        f"```json\n{CODE_SYNTHESIS_JSON_SCHEMA}\n```\n\n"
        "Respond ONLY with the JSON object."
    )


# ──────────────────────────────────────────────────────────────────────────────
# 3.  Test Generation Stage
# ──────────────────────────────────────────────────────────────────────────────

TEST_GENERATION_SYSTEM_PROMPT = """\
You are a senior QA engineer. Given a feature specification and synthesized Python \
source code changes, produce executable Pytest test cases as a JSON object.

CRITICAL TESTING RULES:
1. Exact Imports: Inspect 'Code Changes' and import exact classes/functions defined in 'src/...'.
2. Passing Assertions: Write assertions matching the actual return structures so tests pass.
3. Test Files: Place tests in 'tests/test_unit.py' or 'tests/test_integration.py'.
4. AC Traceability: Map each Acceptance Criterion ID ('AC-NNN') to at least one test.
5. Format: Respond ONLY with a single valid JSON object without markdown fences.

STDLIB-ONLY CONSTRAINT (CRITICAL):
6. The sandbox has NO third-party packages installed. Use ONLY Python stdlib in tests.
7. Allowed test imports: pytest, unittest, unittest.mock, and stdlib modules.
8. NEVER import cryptography, Crypto, pycryptodome, fastapi, flask, requests, httpx, \
pydantic, sqlalchemy, boto3, redis, jwt, bcrypt, or ANY third-party package in test files.
9. Use unittest.mock.patch or unittest.mock.MagicMock to mock any external dependencies.
10. Write tests that are SELF-CONTAINED and pass with zero external dependencies.
11. Each class name in a test file MUST be UNIQUE. Never define the same class name more \
than once in a single file. Use distinct names like TestFeatureCreate, TestFeatureRead, \
TestFeatureValidation for each test group.

MOCK SETUP RULES (CRITICAL — prevents TypeError crashes):
12. When mocking HTTP responses (urlopen, HTTPResponse, etc.), ALWAYS configure \
.read.return_value as BYTES and set up context manager dunder methods. Example:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"status": "ok", "id": "abc123"}'
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
13. When using 'with patch("urllib.request.urlopen") as mock_open:', ALWAYS add:
    mock_open.return_value.read.return_value = b'{"status": "ok", "id": "abc123"}'
    mock_open.return_value.__enter__ = lambda s: mock_open.return_value
    mock_open.return_value.__exit__ = MagicMock(return_value=False)
14. NEVER call json.loads() or response.read().decode() without first configuring \
the mock to return a valid JSON bytes string. MagicMock() default return values \
are NOT strings/bytes and will cause TypeError.
15. Prefer testing class methods directly with simple Python dicts/lists as inputs. \
Only use HTTP mocks when the class under test explicitly makes HTTP calls internally.
16. NEVER directly instantiate HTTP handler classes (e.g. BaseHTTPRequestHandler, \
BaseRequestHandler subclasses) using no-arg constructor. These require 'request', \
'client_address', and 'server' positional arguments AND call handle() in __init__. \
Instead, test the business logic methods directly by calling them on a \
MagicMock(spec=HandlerClass), or skip HTTP handlers and test the underlying service class.
17. ALL functions must include complete type annotations. Always import ALL modules before \
using them at module level. Never write 'os.getenv(...)' without 'import os' at the top."""

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
    plan_dict: dict[str, Any] | None = None,
) -> str:
    """Build the user prompt for the test generation stage."""
    plan_section = (
        f"\n\n## Implementation Plan\n```json\n{json.dumps(plan_dict, indent=2)}\n```"
        if plan_dict
        else ""
    )
    return (
        "Using the feature specification, implementation plan, and code changes below, "
        "generate comprehensive test cases.\n\n"
        "## Feature Specification\n"
        f"```json\n{json.dumps(spec_dict, indent=2)}\n```"
        f"{plan_section}\n\n"
        "## Code Changes\n"
        f"```json\n{json.dumps(changes, indent=2)}\n```\n\n"
        "## Required JSON Schema\n"
        f"```json\n{TEST_GENERATION_JSON_SCHEMA}\n```\n\n"
        "Respond ONLY with the JSON object."
    )
