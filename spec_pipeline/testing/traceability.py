"""Bidirectional Acceptance Criteria Traceability Matrix Builder.

Provides 1:1 and 1:N bidirectional mapping between specification
AcceptanceCriteria (e.g. AC-001, AC-002) and synthesized test functions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spec_pipeline.core.models import FeatureSpec, SynthesizedTest


@dataclass(frozen=True, slots=True)
class TraceabilityEntry:
    """Mapping record for a single Acceptance Criterion."""

    criterion_id: str
    criterion_title: str
    test_ids: list[str] = field(default_factory=list)
    test_functions: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    test_types: list[str] = field(default_factory=list)
    covered: bool = False


@dataclass(frozen=True, slots=True)
class TraceabilityMatrix:
    """Bidirectional traceability matrix connecting Acceptance Criteria and Test Cases."""

    entries: list[TraceabilityEntry]
    criterion_to_tests: dict[str, list[str]]
    test_to_criteria: dict[str, list[str]]
    coverage_ratio: float
    uncovered_criteria: list[str]
    orphan_tests: list[str]

    def render_matrix_markdown(self) -> str:
        """Render a GitHub-flavored Markdown table of the traceability matrix."""
        pct = int(self.coverage_ratio * 100)
        covered_count = len(self.entries) - len(self.uncovered_criteria)
        total_count = len(self.entries)
        lines: list[str] = [
            "### Acceptance Criteria Traceability Matrix",
            f"**Total Coverage**: {pct}% ({covered_count}/{total_count} criteria covered)\n",
            "| Criterion ID | Title | Test Type(s) | Test Function(s) | Status |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]

        for entry in self.entries:
            types_str = ", ".join(sorted(set(entry.test_types))) if entry.test_types else "—"
            funcs_str = (
                "<br>".join(f"`{fn}`" for fn in entry.test_functions)
                if entry.test_functions
                else "—"
            )
            status_str = "✅ Covered" if entry.covered else "❌ Missing"
            row = (
                f"| `{entry.criterion_id}` | {entry.criterion_title} | "
                f"{types_str} | {funcs_str} | {status_str} |"
            )
            lines.append(row)

        if self.orphan_tests:
            lines.append("\n**Unlinked / General Tests**:")
            for ot in self.orphan_tests:
                lines.append(f"- `{ot}`")

        return "\n".join(lines)


class TraceabilityMatrixBuilder:
    """Builds and validates the bidirectional traceability matrix."""

    _TEST_FUNC_REGEX = re.compile(r"def\s+(test_[a-zA-Z0-9_]+)\s*\(", re.MULTILINE)
    _AC_REGEX = re.compile(r"\b(AC-\d+)\b", re.IGNORECASE)

    def extract_test_functions(self, source_code: str) -> list[str]:
        """Extract all `test_*` function names from python source code."""
        return self._TEST_FUNC_REGEX.findall(source_code)

    def build(
        self,
        spec: FeatureSpec,
        tests: list[SynthesizedTest],
    ) -> TraceabilityMatrix:
        """Construct the complete bidirectional TraceabilityMatrix."""
        criterion_to_tests: dict[str, list[str]] = {
            ac.criterion_id: [] for ac in spec.acceptance_criteria
        }
        test_to_criteria: dict[str, list[str]] = {}
        orphan_tests: list[str] = []

        # Map each test and its contained test functions to ACs
        for test in tests:
            funcs = self.extract_test_functions(test.source_code)
            if not funcs:
                funcs = [test.test_id]

            # Find target AC from explicit source_criterion_id or regex in code/docstrings
            target_acs: set[str] = set()
            if test.source_criterion_id:
                target_acs.add(test.source_criterion_id.upper())

            # Also scan test source code & description for AC mentions (e.g. AC-001)
            found_acs = self._AC_REGEX.findall(f"{test.description} {test.source_code}")
            for ac in found_acs:
                target_acs.add(ac.upper())

            # Filter target ACs to those actually in spec
            valid_spec_acs = {
                ac for ac in target_acs if ac in criterion_to_tests
            }

            if valid_spec_acs:
                for ac in valid_spec_acs:
                    for fn in funcs:
                        if fn not in criterion_to_tests[ac]:
                            criterion_to_tests[ac].append(fn)
                        if fn not in test_to_criteria:
                            test_to_criteria[fn] = []
                        if ac not in test_to_criteria[fn]:
                            test_to_criteria[fn].append(ac)
            else:
                for fn in funcs:
                    orphan_tests.append(f"{test.file_path}::{fn}")

        # Build entries
        entries: list[TraceabilityEntry] = []
        uncovered: list[str] = []

        for ac in spec.acceptance_criteria:
            mapped_funcs = criterion_to_tests.get(ac.criterion_id, [])
            mapped_tests = [
                t for t in tests
                if (
                    t.source_criterion_id
                    and t.source_criterion_id.upper() == ac.criterion_id.upper()
                )
                or (ac.criterion_id.upper() in t.source_code.upper())
                or any(fn in mapped_funcs for fn in self.extract_test_functions(t.source_code))
            ]

            test_ids = [t.test_id for t in mapped_tests]
            test_files = list({t.file_path for t in mapped_tests})
            test_types = list({t.test_type for t in mapped_tests})
            is_covered = len(mapped_funcs) > 0 or len(mapped_tests) > 0

            if not is_covered:
                uncovered.append(ac.criterion_id)

            entries.append(
                TraceabilityEntry(
                    criterion_id=ac.criterion_id,
                    criterion_title=ac.title,
                    test_ids=test_ids,
                    test_functions=mapped_funcs,
                    test_files=test_files,
                    test_types=test_types,
                    covered=is_covered,
                )
            )

        total_criteria = len(spec.acceptance_criteria)
        coverage_ratio = (
            (total_criteria - len(uncovered)) / total_criteria if total_criteria > 0 else 1.0
        )

        return TraceabilityMatrix(
            entries=entries,
            criterion_to_tests=criterion_to_tests,
            test_to_criteria=test_to_criteria,
            coverage_ratio=coverage_ratio,
            uncovered_criteria=uncovered,
            orphan_tests=orphan_tests,
        )
