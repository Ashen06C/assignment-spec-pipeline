"""Multi-format specification parser (Markdown, YAML, JSON).

Produces a ``FeatureSpec`` domain model from any supported format and attaches
a deterministic SHA-256 fingerprint of the raw input for auditability.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from spec_pipeline.core.models import (
    AcceptanceCriterion,
    BusinessRule,
    FeatureSpec,
    NonFunctionalRequirement,
    UserStory,
)


class SpecParser:
    """Stateless parser that converts raw specification content into a ``FeatureSpec``."""

    # ── public API ──────────────────────────────────────────────────────── #

    def parse_file(self, path: str | Path) -> FeatureSpec:
        """Auto-detect format by extension and parse.

        Supported extensions: ``.md``, ``.yaml`` / ``.yml``, ``.json``.
        """
        file_path = Path(path)
        raw = file_path.read_text(encoding="utf-8")
        suffix = file_path.suffix.lower()

        if suffix == ".md":
            return self.parse_markdown(raw)
        if suffix in {".yaml", ".yml"}:
            return self.parse_yaml(raw)
        if suffix == ".json":
            return self.parse_json(raw)

        raise ValueError(f"Unsupported spec format: {suffix!r}")

    def parse_markdown(self, raw: str) -> FeatureSpec:
        """Parse a Markdown specification into a ``FeatureSpec``."""
        data = self._markdown_to_dict(raw)
        return self._build_spec(data, raw)

    def parse_yaml(self, raw: str) -> FeatureSpec:
        """Parse a YAML specification into a ``FeatureSpec``."""
        data: dict[str, Any] = yaml.safe_load(raw) or {}
        return self._build_spec(data, raw)

    def parse_json(self, raw: str) -> FeatureSpec:
        """Parse a JSON specification into a ``FeatureSpec``."""
        data: dict[str, Any] = json.loads(raw)
        return self._build_spec(data, raw)

    # ── internal helpers ────────────────────────────────────────────────── #

    @staticmethod
    def compute_hash(raw: str) -> str:
        """Return a deterministic SHA-256 hex digest of *raw*."""
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _build_spec(self, data: dict[str, Any], raw: str) -> FeatureSpec:
        """Normalise parsed dict into a ``FeatureSpec`` and attach the hash."""
        normalised = self._normalise_keys(data)
        spec_hash = self.compute_hash(raw)

        # Map nested structures to their Pydantic models.
        user_stories = [
            UserStory(**self._normalise_keys(s))
            for s in normalised.get("user_stories", [])
        ]
        business_rules = [
            BusinessRule(**self._normalise_keys(r))
            for r in normalised.get("business_rules", [])
        ]
        acceptance_criteria = [
            AcceptanceCriterion(**self._normalise_keys(c))
            for c in normalised.get("acceptance_criteria", [])
        ]
        nfrs = [
            NonFunctionalRequirement(**self._normalise_keys(n))
            for n in normalised.get("non_functional_requirements", [])
        ]

        return FeatureSpec(
            title=normalised.get("title", "Untitled"),
            objective=normalised.get("objective", ""),
            user_stories=user_stories,
            business_rules=business_rules,
            acceptance_criteria=acceptance_criteria,
            non_functional_requirements=nfrs,
            out_of_scope=normalised.get("out_of_scope", []),
            spec_hash=spec_hash,
        )

    # ── Markdown parser ─────────────────────────────────────────────────── #

    _SECTION_HEADING_RE = re.compile(r"^#{1,2}\s+(.+)$", re.MULTILINE)

    @classmethod
    def _markdown_to_dict(cls, raw: str) -> dict[str, Any]:
        """Convert a heading-structured Markdown document into a flat dict.

        Conventions
        -----------
        * ``## Feature Objective`` → ``objective`` (paragraph text)
        * ``## User Story`` / ``## User Stories`` → list of stories
        * ``## Business Rules`` → list of ``{rule_id, description}``
        * ``## Acceptance Criteria`` → list of criteria (Given/When/Then)
        * ``## Non-Functional Requirements`` → list of ``{category, description}``
        * ``## Out of Scope`` → list of strings
        """
        sections = cls._split_sections(raw)
        result: dict[str, Any] = {}

        for heading, body in sections.items():
            key = cls._heading_to_key(heading)
            if key == "title":
                result["title"] = body.strip()
            elif key == "objective":
                result["objective"] = body.strip()
            elif key == "user_stories":
                result["user_stories"] = cls._parse_md_user_stories(body)
            elif key == "business_rules":
                result["business_rules"] = cls._parse_md_business_rules(body)
            elif key == "acceptance_criteria":
                result["acceptance_criteria"] = cls._parse_md_acceptance_criteria(body)
            elif key == "non_functional_requirements":
                result["non_functional_requirements"] = cls._parse_md_nfrs(body)
            elif key == "out_of_scope":
                result["out_of_scope"] = cls._parse_md_list(body)

        # Fall back: use the first H1 as title if not explicitly set.
        if "title" not in result:
            h1_match = re.match(r"^#\s+(.+)$", raw, re.MULTILINE)
            if h1_match:
                result["title"] = h1_match.group(1).strip()

        return result

    @classmethod
    def _split_sections(cls, raw: str) -> dict[str, str]:
        """Split markdown into ``{heading: body}`` pairs."""
        matches = list(cls._SECTION_HEADING_RE.finditer(raw))
        sections: dict[str, str] = {}
        for i, m in enumerate(matches):
            heading = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            sections[heading] = raw[start:end]
        return sections

    @staticmethod
    def _heading_to_key(heading: str) -> str:
        """Map a human heading to its canonical dict key."""
        h = heading.lower().strip()
        mapping: dict[str, str] = {
            "feature objective": "objective",
            "objective": "objective",
            "user story": "user_stories",
            "user stories": "user_stories",
            "business rules": "business_rules",
            "business rule": "business_rules",
            "acceptance criteria": "acceptance_criteria",
            "non-functional requirements": "non_functional_requirements",
            "non functional requirements": "non_functional_requirements",
            "nfrs": "non_functional_requirements",
            "out of scope": "out_of_scope",
            "out-of-scope": "out_of_scope",
        }
        return mapping.get(h, h.replace(" ", "_").replace("-", "_"))

    # ── Markdown section sub-parsers ──────────────────────────────────── #

    @staticmethod
    def _parse_md_user_stories(body: str) -> list[dict[str, str]]:
        """Extract user stories from ``As a … I want … So that …`` blocks."""
        stories: list[dict[str, str]] = []
        pattern = re.compile(
            r"[*\-]?\s*\**As a\**\s+(.+?)"
            r",?\s*\**I want\**\s+(.+?)"
            r",?\s*\**So that\**\s+(.+?)(?:\n|$)",
            re.IGNORECASE,
        )
        for m in pattern.finditer(body):
            stories.append({
                "as_a": m.group(1).strip().rstrip(","),
                "i_want": m.group(2).strip().rstrip(","),
                "so_that": m.group(3).strip().rstrip("."),
            })
        return stories

    @staticmethod
    def _parse_md_business_rules(body: str) -> list[dict[str, str]]:
        """Extract ``BR-NNN: description`` items from a bullet list."""
        rules: list[dict[str, str]] = []
        for line in body.splitlines():
            m = re.match(r"[*\-]\s*(BR-\d+)\s*[:\-–]\s*(.+)", line.strip())
            if m:
                rules.append({"rule_id": m.group(1), "description": m.group(2).strip()})
        return rules

    @staticmethod
    def _parse_md_acceptance_criteria(body: str) -> list[dict[str, str]]:
        """Parse Given/When/Then blocks with optional AC-NNN headers."""
        criteria: list[dict[str, str]] = []
        current: dict[str, str] = {}

        for line in body.splitlines():
            line_s = line.strip()
            # Detect criterion header: "### AC-001: Title" or "- AC-001: Title"
            header_m = re.match(
                r"(?:#{1,4}\s*|[*\-]\s*)(AC-\d+)\s*[:\-–]\s*(.+)", line_s
            )
            if header_m:
                if current:
                    criteria.append(current)
                current = {
                    "criterion_id": header_m.group(1),
                    "title": header_m.group(2).strip(),
                }
                continue

            gwt_m = re.match(
                r"[*\-]?\s*\**(Given|When|Then)\**\s*[:\-–]?\s*(.+)", line_s, re.IGNORECASE
            )
            if gwt_m:
                current[gwt_m.group(1).lower()] = gwt_m.group(2).strip()

        if current:
            criteria.append(current)
        return criteria

    @staticmethod
    def _parse_md_nfrs(body: str) -> list[dict[str, str]]:
        """Parse ``Category: description`` items (with optional threshold)."""
        nfrs: list[dict[str, str]] = []
        for line in body.splitlines():
            m = re.match(r"[*\-]\s*\**(\w[\w\s]*?)\**\s*[:\-–]\s*(.+)", line.strip())
            if m:
                entry: dict[str, str] = {
                    "category": m.group(1).strip().lower(),
                    "description": m.group(2).strip(),
                }
                # Check for an inline threshold in parentheses, e.g. (p99 < 200ms).
                th = re.search(r"\(([^)]+)\)\s*$", entry["description"])
                if th:
                    entry["threshold"] = th.group(1)
                nfrs.append(entry)
        return nfrs

    @staticmethod
    def _parse_md_list(body: str) -> list[str]:
        """Extract simple bullet items."""
        items: list[str] = []
        for line in body.splitlines():
            m = re.match(r"[*\-]\s+(.+)", line.strip())
            if m:
                items.append(m.group(1).strip())
        return items

    # ── key normalisation ────────────────────────────────────────────── #

    @staticmethod
    def _normalise_keys(d: dict[str, Any]) -> dict[str, Any]:
        """Lower-case and snake_case all top-level keys in *d*."""
        out: dict[str, Any] = {}
        for k, v in d.items():
            nk = k.lower().replace(" ", "_").replace("-", "_")
            out[nk] = v
        return out
