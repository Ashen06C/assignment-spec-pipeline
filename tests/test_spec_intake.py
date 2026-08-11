"""Tests for the spec-intake layer — multi-format parsing and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from spec_pipeline.core.exceptions import SpecValidationError
from spec_pipeline.core.models import FeatureSpec
from spec_pipeline.spec_intake.parser import SpecParser
from spec_pipeline.spec_intake.validator import SpecValidator

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "specs"


@pytest.fixture
def parser() -> SpecParser:
    return SpecParser()


@pytest.fixture
def validator() -> SpecValidator:
    return SpecValidator()


def _valid_spec_dict() -> dict:
    """Minimal valid spec as a plain dict (all 6 sections present)."""
    return {
        "title": "Test Feature",
        "objective": "Demonstrate parsing and validation.",
        "user_stories": [
            {"as_a": "developer", "i_want": "to test parsing", "so_that": "it works"}
        ],
        "business_rules": [
            {"rule_id": "BR-001", "description": "Must validate inputs."}
        ],
        "acceptance_criteria": [
            {
                "criterion_id": "AC-001",
                "title": "Input validation",
                "given": "a valid input",
                "when": "submitted",
                "then": "accepted",
            }
        ],
        "non_functional_requirements": [
            {"category": "performance", "description": "Fast response"}
        ],
        "out_of_scope": ["Admin panel"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Parser — JSON
# ──────────────────────────────────────────────────────────────────────────────


class TestParseJson:
    def test_parse_valid_json_string(self, parser: SpecParser) -> None:
        raw = json.dumps(_valid_spec_dict())
        spec = parser.parse_json(raw)
        assert isinstance(spec, FeatureSpec)
        assert spec.title == "Test Feature"
        assert len(spec.user_stories) == 1
        assert spec.user_stories[0].as_a == "developer"

    def test_hash_is_deterministic(self, parser: SpecParser) -> None:
        raw = json.dumps(_valid_spec_dict())
        s1 = parser.parse_json(raw)
        s2 = parser.parse_json(raw)
        assert s1.spec_hash == s2.spec_hash
        assert len(s1.spec_hash) == 64  # SHA-256 hex digest

    def test_different_content_different_hash(self, parser: SpecParser) -> None:
        d1 = _valid_spec_dict()
        d2 = _valid_spec_dict()
        d2["title"] = "Different Title"
        s1 = parser.parse_json(json.dumps(d1))
        s2 = parser.parse_json(json.dumps(d2))
        assert s1.spec_hash != s2.spec_hash

    def test_parse_json_example_file(self, parser: SpecParser) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "audit_logger_service.json")
        assert spec.title == "Audit Logger Service"
        assert len(spec.acceptance_criteria) == 3
        assert spec.acceptance_criteria[0].title == "Event ingestion"


# ──────────────────────────────────────────────────────────────────────────────
# Parser — YAML
# ──────────────────────────────────────────────────────────────────────────────


class TestParseYaml:
    def test_parse_valid_yaml_string(self, parser: SpecParser) -> None:
        raw = yaml.dump(_valid_spec_dict(), default_flow_style=False)
        spec = parser.parse_yaml(raw)
        assert isinstance(spec, FeatureSpec)
        assert spec.objective.startswith("Demonstrate")

    def test_parse_yaml_example_file(self, parser: SpecParser) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "token_bucket_limiter.yaml")
        assert spec.title == "Token Bucket Rate Limiter"
        assert len(spec.user_stories) == 2
        assert len(spec.business_rules) == 3
        assert spec.acceptance_criteria[0].criterion_id == "AC-001"

    def test_yaml_nfr_threshold(self, parser: SpecParser) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "token_bucket_limiter.yaml")
        perf_nfr = spec.non_functional_requirements[0]
        assert perf_nfr.category == "performance"
        assert perf_nfr.threshold == "p99 < 2ms"


# ──────────────────────────────────────────────────────────────────────────────
# Parser — Markdown
# ──────────────────────────────────────────────────────────────────────────────


class TestParseMarkdown:
    def test_parse_markdown_example_file(self, parser: SpecParser) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "rate_limiter.md")
        assert spec.title == "Rate Limiter Service"
        assert "distributed rate-limiting" in spec.objective

    def test_markdown_user_stories(self, parser: SpecParser) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "rate_limiter.md")
        assert len(spec.user_stories) >= 3
        assert spec.user_stories[0].as_a == "platform operator"

    def test_markdown_business_rules(self, parser: SpecParser) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "rate_limiter.md")
        assert len(spec.business_rules) >= 4
        assert spec.business_rules[0].rule_id == "BR-001"

    def test_markdown_acceptance_criteria(self, parser: SpecParser) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "rate_limiter.md")
        assert len(spec.acceptance_criteria) >= 3
        ac1 = spec.acceptance_criteria[0]
        assert ac1.criterion_id == "AC-001"
        assert ac1.title == "Basic rate limiting"
        assert ac1.given
        assert ac1.when
        assert ac1.then

    def test_markdown_nfrs(self, parser: SpecParser) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "rate_limiter.md")
        assert len(spec.non_functional_requirements) >= 3

    def test_markdown_out_of_scope(self, parser: SpecParser) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "rate_limiter.md")
        assert len(spec.out_of_scope) >= 3

    def test_markdown_hash_populated(self, parser: SpecParser) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "rate_limiter.md")
        assert len(spec.spec_hash) == 64


# ──────────────────────────────────────────────────────────────────────────────
# Parser — file extension dispatch
# ──────────────────────────────────────────────────────────────────────────────


class TestParseFileDispatch:
    def test_unsupported_extension_raises(self, parser: SpecParser, tmp_path: Path) -> None:
        bad_file = tmp_path / "spec.txt"
        bad_file.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported spec format"):
            parser.parse_file(bad_file)


# ──────────────────────────────────────────────────────────────────────────────
# Validator — happy path
# ──────────────────────────────────────────────────────────────────────────────


class TestValidatorHappyPath:
    def test_valid_spec_passes(self, parser: SpecParser, validator: SpecValidator) -> None:
        spec = parser.parse_json(json.dumps(_valid_spec_dict()))
        errors = validator.validate(spec)
        assert errors == []

    def test_validate_or_raise_passes(
        self, parser: SpecParser, validator: SpecValidator
    ) -> None:
        spec = parser.parse_json(json.dumps(_valid_spec_dict()))
        validator.validate_or_raise(spec)  # should not raise

    def test_all_example_specs_pass_validation(
        self, parser: SpecParser, validator: SpecValidator
    ) -> None:
        for path in EXAMPLES_DIR.iterdir():
            spec = parser.parse_file(path)
            errors = validator.validate(spec)
            assert errors == [], f"{path.name} failed validation: {errors}"


# ──────────────────────────────────────────────────────────────────────────────
# Validator — missing section failure modes
# ──────────────────────────────────────────────────────────────────────────────


class TestValidatorFailureModes:
    def _make_spec(self, **overrides: object) -> FeatureSpec:
        """Build a FeatureSpec from the valid template, overriding fields."""
        d = _valid_spec_dict()
        d.update(overrides)
        raw = json.dumps(d)
        return SpecParser().parse_json(raw)

    def test_missing_objective(self, validator: SpecValidator) -> None:
        spec = self._make_spec(objective="")
        errors = validator.validate(spec)
        assert any("Feature Objective" in e for e in errors)

    def test_missing_user_stories(self, validator: SpecValidator) -> None:
        with pytest.raises(ValidationError):
            # Pydantic min_length=1 will reject this at parse time
            self._make_spec(user_stories=[])

    def test_missing_business_rules(self, validator: SpecValidator) -> None:
        with pytest.raises(ValidationError):
            self._make_spec(business_rules=[])

    def test_missing_acceptance_criteria(self, validator: SpecValidator) -> None:
        with pytest.raises(ValidationError):
            self._make_spec(acceptance_criteria=[])

    def test_missing_nfrs(self, validator: SpecValidator) -> None:
        with pytest.raises(ValidationError):
            self._make_spec(non_functional_requirements=[])

    def test_missing_out_of_scope(self, validator: SpecValidator) -> None:
        with pytest.raises(ValidationError):
            self._make_spec(out_of_scope=[])

    def test_validate_or_raise_raises(self, validator: SpecValidator) -> None:
        spec = self._make_spec(objective="")
        with pytest.raises(SpecValidationError) as exc_info:
            validator.validate_or_raise(spec)
        assert "Feature Objective" in str(exc_info.value)

    def test_malformed_user_story_fields(self, validator: SpecValidator) -> None:
        spec = self._make_spec(
            user_stories=[{"as_a": "", "i_want": "something", "so_that": "reason"}]
        )
        errors = validator.validate(spec)
        assert any("User Story" in e for e in errors)

    def test_malformed_business_rule_fields(self, validator: SpecValidator) -> None:
        spec = self._make_spec(
            business_rules=[{"rule_id": "BR-001", "description": ""}]
        )
        errors = validator.validate(spec)
        assert any("Business Rule" in e for e in errors)

    def test_malformed_acceptance_criterion_fields(self, validator: SpecValidator) -> None:
        spec = self._make_spec(
            acceptance_criteria=[{
                "criterion_id": "AC-001",
                "title": "Test",
                "given": "setup",
                "when": "",
                "then": "result",
            }]
        )
        errors = validator.validate(spec)
        assert any("Acceptance Criterion" in e for e in errors)

    def test_malformed_nfr_fields(self, validator: SpecValidator) -> None:
        spec = self._make_spec(
            non_functional_requirements=[{"category": "", "description": "something"}]
        )
        errors = validator.validate(spec)
        assert any("Non-Functional Requirement" in e for e in errors)


# ──────────────────────────────────────────────────────────────────────────────
# Hash determinism
# ──────────────────────────────────────────────────────────────────────────────


class TestHashDeterminism:
    def test_compute_hash_consistency(self) -> None:
        raw = "some deterministic content"
        h1 = SpecParser.compute_hash(raw)
        h2 = SpecParser.compute_hash(raw)
        assert h1 == h2

    def test_hash_changes_with_content(self) -> None:
        assert SpecParser.compute_hash("a") != SpecParser.compute_hash("b")
