"""AI-assisted code synthesizer orchestrating generation, governance checks, and safe patching."""

from __future__ import annotations

from typing import TYPE_CHECKING

from spec_pipeline.core.config import load_settings

if TYPE_CHECKING:
    from pathlib import Path
from spec_pipeline.core.models import (
    FeatureSpec,
    FileChange,
    ImplementationOutput,
    ImplementationPlan,
)
from spec_pipeline.governance.sandbox_policy import SandboxPolicyEnforcer
from spec_pipeline.implementation.patch_engine import PatchEngine
from spec_pipeline.llm import BaseLLMProvider, LLMConfig, get_llm_provider
from spec_pipeline.llm.json_util import parse_llm_json
from spec_pipeline.llm.prompt_templates import (
    CODE_SYNTHESIS_SYSTEM_PROMPT,
    build_code_synthesis_prompt,
)


class CodeSynthesizer:
    """Orchestrates AI-driven code generation with strict sandbox governance."""

    def __init__(
        self,
        llm: BaseLLMProvider | None = None,
        policy_enforcer: SandboxPolicyEnforcer | None = None,
        patch_engine: PatchEngine | None = None,
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

        self.policy_enforcer = policy_enforcer or SandboxPolicyEnforcer()
        self.patch_engine = patch_engine or PatchEngine()

    def synthesize(
        self,
        spec: FeatureSpec,
        plan: ImplementationPlan,
        sandbox_root: str | Path | None = None,
    ) -> ImplementationOutput:
        """Generate code changes from *spec* and *plan*, enforcing blast radius boundaries.

        Parameters
        ----------
        spec:
            The approved feature specification.
        plan:
            The approved technical implementation plan.
        sandbox_root:
            Optional sandbox directory to immediately apply and verify file patches.

        Returns
        -------
        ImplementationOutput
            The synthesized changes, diff summaries, and overall metadata.

        Raises
        ------
        SandboxPolicyViolationError
            If generated changes attempt path traversal or exceed approved blast radius.
        """
        spec_dict = spec.model_dump(mode="json")
        plan_dict = plan.model_dump(mode="json")

        prompt = build_code_synthesis_prompt(spec_dict, plan_dict)
        raw_response, _usage = self.llm.generate(
            prompt,
            system_prompt=CODE_SYNTHESIS_SYSTEM_PROMPT,
        )

        output_data = parse_llm_json(raw_response)
        if not isinstance(output_data, dict):
            raise ValueError("Expected JSON object from LLM code synthesis response")

        raw_changes = output_data.get("changes", [])
        all_changes: list[FileChange] = [
            FileChange(**c) for c in raw_changes if isinstance(c, dict)
        ]

        # Isolate and filter to approved impacted files whitelist
        allowed_set = set(plan.impacted_files) if plan.impacted_files else set()
        if allowed_set:
            changes = [
                c for c in all_changes
                if c.path in allowed_set or c.path.lstrip("./") in allowed_set
            ]
            if not changes:
                changes = all_changes
        else:
            changes = all_changes

        # Post-process: rewrite third-party imports to stdlib equivalents,
        # then ensure any used-but-not-imported stdlib modules are added.
        for change in changes:
            if change.content:
                change.content = self._sanitize_content(change.content)
                change.content = self._ensure_stdlib_imports(change.content)

        # 1. Strict Sandbox Policy Verification
        self.policy_enforcer.validate_changes(
            changes,
            allowed_files=plan.impacted_files,
        )

        # 2. Apply Patches to Sandbox if requested
        if sandbox_root is not None:
            changes = self.patch_engine.apply_changes(changes, sandbox_root)

        change_summary = output_data.get(
            "change_summary",
            f"Generated {len(changes)} code changes for '{spec.title}'.",
        )

        return ImplementationOutput(
            plan_id=plan.plan_id,
            changes=changes,
            change_summary=change_summary,
        )

    @staticmethod
    def _sanitize_content(content: str) -> str:
        """Rewrite forbidden third-party imports to stdlib equivalents.

        The LLM sometimes generates third-party imports despite prompt instructions.
        This post-processor catches the most common offenders and replaces them with
        stdlib alternatives so the sandbox can always execute without pip installs.
        """
        import re  # noqa: PLC0415 (local import intentional — avoids top-level cycle)

        # Map of (regex pattern, stdlib replacement comment block)
        _stdlib_replacements: list[tuple[str, str]] = [
            # JWT → stdlib HMAC/hashlib-based token handling
            (
                r"^import jwt\b.*$",
                (
                    "import hmac  # stdlib replacement: jwt replaced with hmac+hashlib\n"
                    "import hashlib\n"
                    "import base64\n"
                    "import json as _json_mod"
                ),
            ),
            (r"^from jwt\b.*$", "# jwt import removed: use hmac/hashlib for token signing"),
            # cryptography → stdlib hashlib/hmac/secrets
            (
                r"^(?:import|from) cryptography\b.*$",
                "import hashlib  # stdlib replacement: cryptography → hashlib/hmac",
            ),
            # bcrypt → stdlib hashlib
            (
                r"^(?:import|from) bcrypt\b.*$",
                "import hashlib  # stdlib replacement: bcrypt → hashlib.sha256",
            ),
            # passlib → stdlib hashlib
            (
                r"^(?:import|from) passlib\b.*$",
                "import hashlib  # stdlib replacement: passlib → hashlib",
            ),
            # requests / httpx → stdlib urllib
            (
                r"^import requests\b.*$",
                "import urllib.request  # stdlib replacement: requests → urllib",
            ),
            (
                r"^from requests\b.*$",
                "import urllib.request  # stdlib replacement: requests → urllib",
            ),
            (
                r"^import httpx\b.*$",
                "import urllib.request  # stdlib replacement: httpx → urllib",
            ),
            (
                r"^from httpx\b.*$",
                "import urllib.request  # stdlib replacement: httpx → urllib",
            ),
            # pydantic → stdlib dataclasses
            (
                r"^(?:import|from) pydantic\b.*$",
                # stdlib replacement: pydantic → dataclasses
                "from dataclasses import dataclass, field",
            ),
            # sqlalchemy → stdlib sqlite3
            (
                r"^(?:import|from) sqlalchemy\b.*$",
                "import sqlite3  # stdlib replacement: sqlalchemy → sqlite3",
            ),
            # fastapi / starlette / uvicorn → stdlib http.server
            (
                r"^(?:import|from) fastapi\b.*$",
                "import http.server  # stdlib replacement: fastapi → http.server",
            ),
            (
                r"^(?:import|from) starlette\b.*$",
                "# starlette import removed: using stdlib http.server",
            ),
            (
                r"^(?:import|from) uvicorn\b.*$",
                "# uvicorn import removed: using stdlib http.server",
            ),
            # flask / django
            (
                r"^(?:import|from) flask\b.*$",
                "import http.server  # stdlib replacement: flask → http.server",
            ),
            (
                r"^(?:import|from) django\b.*$",
                "# django import removed: using stdlib http.server",
            ),
            # pycryptodome (Crypto) → stdlib hashlib/hmac
            (
                r"^(?:import|from) Crypto\b.*$",
                "import hashlib  # stdlib replacement: pycryptodome → hashlib/hmac",
            ),
            (
                r"^(?:import|from) Cryptodome\b.*$",
                "import hashlib  # stdlib replacement: Cryptodome → hashlib/hmac",
            ),
            # redis / celery / boto3
            (r"^(?:import|from) redis\b.*$", "# redis import removed (not available in sandbox)"),
            (r"^(?:import|from) celery\b.*$", "# celery import removed (not available in sandbox)"),
            (r"^(?:import|from) boto3\b.*$", "# boto3 import removed (not available in sandbox)"),
            # numpy / pandas
            (r"^import numpy\b.*$", "import array  # stdlib replacement: numpy → array"),
            (r"^from numpy\b.*$", "# numpy import removed: use stdlib array/math"),
            (r"^import pandas\b.*$", "import csv  # stdlib replacement: pandas → csv"),
            (r"^from pandas\b.*$", "# pandas import removed: use stdlib csv"),
            # yaml / toml
            (r"^import yaml\b.*$", "import json  # stdlib replacement: PyYAML → json"),
            (r"^from yaml\b.*$", "import json  # stdlib replacement: PyYAML → json"),
            (r"^import toml\b.*$", "import json  # stdlib replacement: toml → json"),
            # aiofiles / aiohttp
            (r"^import aiofiles\b.*$", "# aiofiles removed: use stdlib open()"),
            (r"^from aiofiles\b.*$", "# aiofiles removed: use stdlib open()"),
            # marshmallow / attrs
            (
                r"^(?:import|from) marshmallow\b.*$",
                "from dataclasses import dataclass, field  # stdlib: marshmallow → dataclasses",
            ),
            (
                r"^(?:import|from) attr\b.*$",
                "from dataclasses import dataclass, field  # stdlib: attrs → dataclasses",
            ),
            # arrow / pendulum (datetime alternatives)
            (r"^import arrow\b.*$", "import datetime  # stdlib replacement: arrow → datetime"),
            (r"^from arrow\b.*$", "import datetime  # stdlib replacement: arrow → datetime"),
            # motor / pymongo
            (r"^(?:import|from) motor\b.*$", "# motor removed (not available in sandbox)"),
            (r"^(?:import|from) pymongo\b.*$", "# pymongo removed (not available in sandbox)"),
            # click / typer (CLI)
            (r"^import click\b.*$", "import argparse  # stdlib replacement: click → argparse"),
            (r"^from click\b.*$", "import argparse  # stdlib replacement: click → argparse"),
            (r"^import typer\b.*$", "import argparse  # stdlib replacement: typer → argparse"),
        ]

        lines = content.splitlines()
        result: list[str] = []
        seen_replacements: set[str] = set()

        for line in lines:
            replaced = False
            for pattern, replacement in _stdlib_replacements:
                if re.match(pattern, line.strip()):
                    # Avoid duplicate replacement lines (e.g. multiple jwt imports)
                    if replacement not in seen_replacements:
                        result.append(replacement)
                        seen_replacements.add(replacement)
                    replaced = True
                    break
            if not replaced:
                result.append(line)

        return "\n".join(result)

    @staticmethod
    def _ensure_stdlib_imports(content: str) -> str:
        """Auto-insert missing stdlib import statements.

        The LLM frequently writes ``os.getenv(...)``, ``re.sub(...)``, etc. at module
        level without the corresponding ``import os`` / ``import re``.  This method
        detects those usages and prepends the missing import right after the last
        existing import line so the sandbox file can be executed without NameError.
        """
        import re  # noqa: PLC0415

        # Map of module name → regex that detects usage in source code
        _stdlib_usage: dict[str, str] = {
            "os":          r"\bos\s*\.",
            "sys":         r"\bsys\s*\.",
            "re":          r"\bre\s*\.",
            "json":        r"\bjson\s*\.",
            "time":        r"\btime\s*\.",
            "hashlib":     r"\bhashlib\s*\.",
            "hmac":        r"\bhmac\s*\.",
            "uuid":        r"\buuid\s*\.",
            "logging":     r"\blogging\s*\.",
            "math":        r"\bmath\s*\.",
            "random":      r"\brandom\s*\.",
            "base64":      r"\bbase64\s*\.",
            "threading":   r"\bthreading\s*\.",
            "io":          r"\bio\s*\.",
            "socket":      r"\bsocket\s*\.",
            "struct":      r"\bstruct\s*\.",
            "subprocess":  r"\bsubprocess\s*\.",
            "sqlite3":     r"\bsqlite3\s*\.",
            "csv":         r"\bcsv\s*\.",
            "argparse":    r"\bargparse\s*\.",
            "traceback":   r"\btraceback\s*\.",
            "inspect":     r"\binspect\s*\.",
            "secrets":     r"\bsecrets\s*\.",
            "copy":        r"\bcopy\s*\.",
            "string":      r"\bstring\s*\.",
            "signal":      r"\bsignal\s*\.",
            "pathlib":     r"\bPath\s*\(",
            "datetime":    r"\bdatetime\s*\.",
            "typing":      r"\bOptional\b|\bList\b|\bDict\b|\bTuple\b|\bUnion\b|\bAny\b",
            "collections": r"\bcollections\s*\.",
            "functools":   r"\bfunctools\s*\.",
            "itertools":   r"\bitertools\s*\.",
            "contextlib":  r"\bcontextlib\s*\.",
            "abc":         r"\bABC\b|\bABCMeta\b|\babstractmethod\b",
            "enum":        r"\bEnum\b|\bIntEnum\b",
            "http":        r"\bhttp\s*\.",
            "urllib":      r"\burllib\s*\.",
        }

        missing: list[str] = []
        for module, usage_pattern in _stdlib_usage.items():
            if not re.search(usage_pattern, content):
                continue
            # Already imported?
            already = re.search(
                rf"^(?:import\s+{re.escape(module)}\b|from\s+{re.escape(module)}\s)",
                content,
                re.MULTILINE,
            )
            if not already:
                missing.append(module)

        if not missing:
            return content

        # Find insertion point: just after the last import/from/# line at the top
        lines = content.splitlines()
        insert_idx = 0
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith(("import ", "from ", "from __future__")):
                insert_idx = i + 1
            elif s.startswith("#") or s == "":
                if insert_idx > 0:
                    insert_idx = i + 1
            elif insert_idx > 0:
                break  # first non-import non-blank non-comment line after imports

        for mod in sorted(missing):
            lines.insert(insert_idx, f"import {mod}  # auto-added: was used but not imported")
            insert_idx += 1

        return "\n".join(lines)
