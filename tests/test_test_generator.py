import ast

import pytest

from orchestrator.test_generator import (
    build_generation_prompt,
    extract_python_from_response,
)
from orchestrator.models import ParsedSpec, ConstraintSet, TaskConstraints


# --- Unit tests: prompt construction and code extraction ---


class TestBuildGenerationPrompt:
    def test_build_generation_prompt_contains_name_and_pytest(self, minimal_spec, minimal_constraints):
        prompt = build_generation_prompt(minimal_spec, minimal_constraints)
        assert isinstance(prompt, str)
        assert minimal_spec.name in prompt
        assert "pytest" in prompt.lower()

    def test_build_generation_prompt_includes_primary_constraints(self, minimal_spec, minimal_constraints):
        prompt = build_generation_prompt(minimal_spec, minimal_constraints)
        assert str(minimal_constraints.primary.max_cyclomatic_complexity) in prompt

    def test_build_generation_prompt_includes_secondary_constraints(self, minimal_spec, minimal_constraints):
        prompt = build_generation_prompt(minimal_spec, minimal_constraints)
        assert "docstring" in prompt.lower()

    def test_build_generation_prompt_includes_examples(self, minimal_spec, minimal_constraints):
        prompt = build_generation_prompt(minimal_spec, minimal_constraints)
        assert "1, 2" in prompt or "(1, 2)" in prompt

    def test_build_generation_prompt_distinguishes_primary_and_secondary(self, minimal_spec, minimal_constraints):
        prompt = build_generation_prompt(minimal_spec, minimal_constraints)
        assert "primary" in prompt.lower()
        assert "secondary" in prompt.lower()

    def test_build_generation_prompt_includes_guidance(self, minimal_spec):
        constraints = TaskConstraints(
            primary=ConstraintSet(max_cyclomatic_complexity=5),
            secondary=ConstraintSet(),
            target_files=[],
            guidance=["Prefer early returns.", "Avoid inline comments."],
        )
        prompt = build_generation_prompt(minimal_spec, constraints)
        assert "Prefer early returns." in prompt
        assert "Avoid inline comments." in prompt

    def test_build_generation_prompt_includes_time_complexity(self, minimal_spec):
        constraints = TaskConstraints(
            primary=ConstraintSet(max_time_complexity="O(n)"),
            secondary=ConstraintSet(),
            target_files=[],
        )
        prompt = build_generation_prompt(minimal_spec, constraints)
        assert "O(n)" in prompt


class TestExtractPythonFromResponse:
    def test_extract_python_from_code_fence(self):
        response = 'Here are the tests:\n\n```python\nimport pytest\n\ndef test_add():\n    assert 1 + 1 == 2\n```\n\nDone.'
        code = extract_python_from_response(response)
        assert "import pytest" in code
        assert "def test_add" in code

    def test_extract_python_from_raw_code(self):
        response = 'import pytest\n\ndef test_add():\n    assert 1 + 1 == 2\n'
        code = extract_python_from_response(response)
        assert "import pytest" in code

    def test_extract_python_from_response_validates_syntax(self):
        response = '```python\nimport pytest\n\ndef test_add():\n    assert 1 + 1 == 2\n```'
        code = extract_python_from_response(response)
        ast.parse(code)

    def test_extract_python_from_response_multiple_code_blocks(self):
        response = '```python\nimport pytest\n```\n\nAnd more:\n\n```python\ndef test_add():\n    assert 1 + 1 == 2\n```'
        code = extract_python_from_response(response)
        assert "def test_" in code
