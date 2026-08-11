"""Specification validator enforcing the 6-section Newton Russell standard.

Mandatory sections
------------------
1. Feature Objective   — non-empty string
2. User Stories        — ≥ 1 entry with ``as_a``, ``i_want``, ``so_that``
3. Business Rules      — ≥ 1 entry with ``rule_id``, ``description``
4. Acceptance Criteria — ≥ 1 entry with ``criterion_id``, ``title``, ``given``, ``when``, ``then``
5. Non-Functional Req. — ≥ 1 entry with ``category``, ``description``
6. Out-of-Scope Items  — ≥ 1 string item
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from spec_pipeline.core.exceptions import SpecValidationError

if TYPE_CHECKING:
    from spec_pipeline.core.models import FeatureSpec


class SpecValidator:
    """Validates a ``FeatureSpec`` against the Newton Russell specification standard."""

    # Sub-model required fields — used for structural checks.
    _USER_STORY_FIELDS = {"as_a", "i_want", "so_that"}
    _BUSINESS_RULE_FIELDS = {"rule_id", "description"}
    _ACCEPTANCE_CRITERION_FIELDS = {"criterion_id", "title", "given", "when", "then"}
    _NFR_FIELDS = {"category", "description"}

    def validate(self, spec: FeatureSpec) -> list[str]:
        """Return a list of human-readable validation errors (empty = valid).

        Does **not** raise — use :meth:`validate_or_raise` for fail-fast behaviour.
        """
        errors: list[str] = []

        # 1. Feature Objective
        if not spec.objective or not spec.objective.strip():
            errors.append("Missing or empty: Feature Objective")

        # 2. User Stories
        if not spec.user_stories:
            errors.append("Missing: User Stories (at least 1 required)")
        else:
            for i, story in enumerate(spec.user_stories):
                missing = self._missing_fields(story, self._USER_STORY_FIELDS)
                if missing:
                    errors.append(
                        f"User Story [{i}] missing fields: {', '.join(sorted(missing))}"
                    )

        # 3. Business Rules
        if not spec.business_rules:
            errors.append("Missing: Business Rules (at least 1 required)")
        else:
            for i, rule in enumerate(spec.business_rules):
                missing = self._missing_fields(rule, self._BUSINESS_RULE_FIELDS)
                if missing:
                    errors.append(
                        f"Business Rule [{i}] missing fields: {', '.join(sorted(missing))}"
                    )

        # 4. Acceptance Criteria
        if not spec.acceptance_criteria:
            errors.append("Missing: Acceptance Criteria (at least 1 required)")
        else:
            for i, crit in enumerate(spec.acceptance_criteria):
                missing = self._missing_fields(crit, self._ACCEPTANCE_CRITERION_FIELDS)
                if missing:
                    errors.append(
                        f"Acceptance Criterion [{i}] missing fields: "
                        f"{', '.join(sorted(missing))}"
                    )

        # 5. Non-Functional Requirements
        if not spec.non_functional_requirements:
            errors.append(
                "Missing: Non-Functional Requirements (at least 1 required)"
            )
        else:
            for i, nfr in enumerate(spec.non_functional_requirements):
                missing = self._missing_fields(nfr, self._NFR_FIELDS)
                if missing:
                    errors.append(
                        f"Non-Functional Requirement [{i}] missing fields: "
                        f"{', '.join(sorted(missing))}"
                    )

        # 6. Out-of-Scope Items
        if not spec.out_of_scope:
            errors.append("Missing: Out-of-Scope Items (at least 1 required)")

        return errors

    def validate_or_raise(self, spec: FeatureSpec) -> None:
        """Validate *spec* and raise ``SpecValidationError`` on failure."""
        errors = self.validate(spec)
        if errors:
            raise SpecValidationError(missing_sections=errors, message="\n".join(errors))

    # ── helpers ─────────────────────────────────────────────────────────── #

    @staticmethod
    def _missing_fields(model: Any, required: set[str]) -> set[str]:
        """Return the subset of *required* fields that are empty or absent."""
        missing: set[str] = set()
        for field in required:
            value = getattr(model, field, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.add(field)
        return missing
