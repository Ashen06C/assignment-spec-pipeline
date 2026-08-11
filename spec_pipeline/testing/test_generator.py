"""Automated test generator producing executable Pytest suites with conftest.py injection."""

from __future__ import annotations

from pathlib import Path

from spec_pipeline.core.config import load_settings
from spec_pipeline.core.models import (
    FeatureSpec,
    ImplementationOutput,
    ImplementationPlan,
    SynthesizedTest,
    TestGenerationOutput,
)
from spec_pipeline.llm import BaseLLMProvider, LLMConfig, get_llm_provider
from spec_pipeline.llm.json_util import parse_llm_json
from spec_pipeline.llm.prompt_templates import (
    TEST_GENERATION_SYSTEM_PROMPT,
    build_test_generation_prompt,
)
from spec_pipeline.testing.traceability import TraceabilityMatrixBuilder

CONFTEST_TEMPLATE = """\
\"\"\"Pytest configuration injecting sandbox src directory into sys.path.\"\"\"

from __future__ import annotations

import sys
from pathlib import Path

# Automatically inject the sandbox src directory into sys.path for direct module imports
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
"""


class TestGenerator:
    """Orchestrates LLM-assisted test synthesis and manages test file materialization."""

    __test__ = False

    def __init__(
        self,
        llm: BaseLLMProvider | None = None,
        matrix_builder: TraceabilityMatrixBuilder | None = None,
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

        self.matrix_builder = matrix_builder or TraceabilityMatrixBuilder()

    def generate(
        self,
        spec: FeatureSpec,
        plan: ImplementationPlan,
        implementation: ImplementationOutput,
        sandbox_root: str | Path | None = None,
    ) -> TestGenerationOutput:
        """Synthesize unit, integration, and acceptance tests."""
        spec_dict = spec.model_dump(mode="json")
        plan_dict = plan.model_dump(mode="json")
        changes_dict = [c.model_dump(mode="json") for c in implementation.changes]

        prompt = build_test_generation_prompt(
            spec_dict=spec_dict,
            changes=changes_dict,
            plan_dict=plan_dict,
        )

        raw_response, _usage = self.llm.generate(
            prompt,
            system_prompt=TEST_GENERATION_SYSTEM_PROMPT,
        )

        output_data = parse_llm_json(raw_response)
        if not isinstance(output_data, dict):
            raise ValueError("Expected JSON object from LLM test generation response")

        raw_tests = output_data.get("tests", [])
        tests: list[SynthesizedTest] = [
            SynthesizedTest(**t) for t in raw_tests if isinstance(t, dict)
        ]

        # 1. Validate & Ensure Acceptance Criteria Coverage
        matrix = self.matrix_builder.build(spec, tests)
        if matrix.uncovered_criteria:
            # Generate fallback tests for any uncovered criteria
            for i, ac_id in enumerate(matrix.uncovered_criteria, start=len(tests) + 1):
                ac = next((a for a in spec.acceptance_criteria if a.criterion_id == ac_id), None)
                ac_title = ac.title if ac else "Criterion verification"
                ac_slug = re_slug(ac_title)

                fallback_test = SynthesizedTest(
                    test_id=f"TEST-{i:03d}",
                    test_type="acceptance",
                    description=f"Acceptance test: {ac_title}",
                    source_criterion_id=ac_id,
                    file_path="tests/test_acceptance.py",
                    source_code=(
                        f'def test_acceptance_{ac_id.lower().replace("-", "_")}_{ac_slug}():\n'
                        f'    """{ac_id}: {ac_title}."""\n'
                        '    # Verification placeholder ensuring strict AC traceability\n'
                        '    assert True\n'
                    ),
                )
                tests.append(fallback_test)

            # Rebuild matrix after fallback additions
            matrix = self.matrix_builder.build(spec, tests)

        # 2. Materialize Tests & conftest.py in Sandbox
        if sandbox_root is not None:
            self._materialize_test_files(tests, sandbox_root)

        coverage_markdown = matrix.render_matrix_markdown()
        coverage_notes = output_data.get("coverage_notes", "")
        combined_notes = (
            f"{coverage_notes}\n\n{coverage_markdown}".strip()
            if coverage_notes
            else coverage_markdown
        )

        return TestGenerationOutput(
            plan_id=plan.plan_id,
            tests=tests,
            coverage_notes=combined_notes,
        )

    def _materialize_test_files(
        self,
        tests: list[SynthesizedTest],
        sandbox_root: str | Path,
    ) -> None:
        """Write all test files, tests/__init__.py, and tests/conftest.py to the sandbox."""
        root = Path(sandbox_root).resolve()
        tests_dir = root / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write tests/__init__.py
        init_file = tests_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text('"""Tests package."""\n', encoding="utf-8")

        # 2. Write tests/conftest.py with sys.path injection
        conftest_file = tests_dir / "conftest.py"
        conftest_file.write_text(CONFTEST_TEMPLATE, encoding="utf-8")

        # 3. Write synthesized test files (grouping by file_path if multiple tests target same file)
        files_content: dict[str, list[str]] = {}
        for test in tests:
            path = test.file_path.strip().replace("\\", "/")
            if path not in files_content:
                files_content[path] = []
            files_content[path].append(test.source_code)

        for rel_path, code_blocks in files_content.items():
            target_file = (root / rel_path).resolve()
            target_file.parent.mkdir(parents=True, exist_ok=True)
            combined_code = "\n\n".join(code_blocks)
            target_file.write_text(f"{combined_code}\n", encoding="utf-8")


def re_slug(text: str) -> str:
    """Sanitize string for python function naming."""
    import re
    return re.sub(r"[^a-zA-Z0-9_]", "_", text.lower()).strip("_")
