"""Tests for the prompt builders module."""

from pathlib import Path

from orchestrator.models import ParsedSpec
from orchestrator.prompts import (
    build_critic_prompt,
    build_exploit_prompt,
    build_generation_prompt,
    build_implementation_prompt,
)


class TestBuildGenerationPrompt:
    """Tests for build_generation_prompt."""

    def test_contains_function_name(self, minimal_spec, minimal_constraints):
        """Test that the prompt contains the function name.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
            minimal_constraints: Minimal TaskConstraints fixture.
        """
        prompt = build_generation_prompt(minimal_spec, minimal_constraints)
        assert minimal_spec.name in prompt

    def test_contains_description(self, minimal_spec, minimal_constraints):
        """Test that the prompt contains the spec description.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
            minimal_constraints: Minimal TaskConstraints fixture.
        """
        prompt = build_generation_prompt(minimal_spec, minimal_constraints)
        assert minimal_spec.description in prompt

    def test_contains_pytest_instruction(self, minimal_spec, minimal_constraints):
        """Test that the prompt instructs to write pytest tests.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
            minimal_constraints: Minimal TaskConstraints fixture.
        """
        prompt = build_generation_prompt(minimal_spec, minimal_constraints)
        assert "pytest" in prompt

    def test_includes_constraint_feedback(self, minimal_spec, minimal_constraints):
        """Test that constraint feedback is appended when provided.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
            minimal_constraints: Minimal TaskConstraints fixture.
        """
        prompt = build_generation_prompt(
            minimal_spec, minimal_constraints,
            constraint_feedback="missing docstring on test_add",
        )
        assert "missing docstring" in prompt
        assert "violation" in prompt.lower()

    def test_includes_critique_feedback(self, minimal_spec, minimal_constraints):
        """Test that critique feedback is appended when provided.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
            minimal_constraints: Minimal TaskConstraints fixture.
        """
        prompt = build_generation_prompt(
            minimal_spec, minimal_constraints,
            critique_feedback="Exploit vectors: hardcoded return 3",
        )
        assert "hardcoded return 3" in prompt
        assert "CRITIC" in prompt

    def test_hidden_evals_not_included(self, minimal_constraints):
        """Test that hidden eval literals are not leaked to generation prompt.

        Args:
            minimal_constraints: Minimal TaskConstraints fixture.
        """
        spec = ParsedSpec(
            name="add",
            description="Add numbers",
            public_evals=[{"input": "(1, 2)", "output": "3"}],
            hidden_evals=[{"input": "(999, 1)", "output": "1000"}],
        )
        prompt = build_generation_prompt(spec, minimal_constraints)
        assert "(1, 2)" in prompt
        assert "999" not in prompt
        assert "1000" not in prompt


class TestBuildCriticPrompt:
    """Tests for build_critic_prompt."""

    def test_contains_test_source(self, minimal_spec):
        """Test that the critic prompt includes the test source code.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
        """
        test_code = "def test_add():\n    assert add(1, 2) == 3"
        prompt = build_critic_prompt(test_code, minimal_spec)
        assert "test_add" in prompt
        assert "assert add(1, 2) == 3" in prompt

    def test_contains_spec_description(self, minimal_spec):
        """Test that the critic prompt includes the spec description.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
        """
        prompt = build_critic_prompt("test code", minimal_spec)
        assert minimal_spec.description in prompt

    def test_requests_json_output(self, minimal_spec):
        """Test that the critic prompt requests JSON output.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
        """
        prompt = build_critic_prompt("test code", minimal_spec)
        assert "JSON" in prompt

    def test_includes_constraints_when_provided(
        self, minimal_spec, minimal_constraints
    ):
        """Test that constraints are included when passed.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
            minimal_constraints: Minimal TaskConstraints fixture.
        """
        prompt = build_critic_prompt(
            "test code", minimal_spec, constraints=minimal_constraints
        )
        assert "cyclomatic complexity" in prompt.lower() or "primary" in prompt.lower()

    def test_works_without_constraints(self, minimal_spec):
        """Test that the prompt works when constraints is None.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
        """
        prompt = build_critic_prompt("test code", minimal_spec, constraints=None)
        assert "red-team" in prompt.lower() or "critic" in prompt.lower()

    def test_hidden_evals_not_included(self, minimal_constraints):
        """Test that hidden eval literals are not leaked to critic prompt.

        Args:
            minimal_constraints: Minimal TaskConstraints fixture.
        """
        spec = ParsedSpec(
            name="add",
            description="Add numbers",
            public_evals=[{"input": "(1, 2)", "output": "3"}],
            hidden_evals=[{"input": "(555, 7)", "output": "562"}],
        )
        prompt = build_critic_prompt("def test_add(): pass", spec, minimal_constraints)
        assert "(1, 2)" in prompt
        assert "555" not in prompt
        assert "562" not in prompt


class TestBuildExploitPrompt:
    """Tests for build_exploit_prompt."""

    def test_build_exploit_prompt_contains_spec_description(self, minimal_spec):
        """Test that build_exploit_prompt includes the spec description.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
        """
        prompt = build_exploit_prompt(
            "def test_add(): assert add(1, 2) == 3",
            minimal_spec,
        )
        assert minimal_spec.description in prompt

    def test_build_exploit_prompt_includes_test_source(self, minimal_spec):
        """Test that build_exploit_prompt includes the test source code.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
        """
        test_code = "def test_add():\n    assert add(1, 2) == 3"
        prompt = build_exploit_prompt(test_code, minimal_spec)
        assert "test_add" in prompt
        assert "assert add(1, 2) == 3" in prompt

    def test_hidden_evals_not_included(self):
        """Test that hidden eval literals are not leaked to exploit prompt."""
        spec = ParsedSpec(
            name="add",
            description="Add numbers",
            public_evals=[{"input": "(1, 2)", "output": "3"}],
            hidden_evals=[{"input": "(321, 123)", "output": "444"}],
        )
        prompt = build_exploit_prompt("def test_add(): pass", spec)
        assert "(1, 2)" in prompt
        assert "321" not in prompt
        assert "444" not in prompt


class TestBuildImplementationPrompt:
    """Tests for build_implementation_prompt."""

    def test_basic_prompt_contains_test_paths(self):
        """Test that the prompt lists the test file paths."""
        paths = [Path("tests/test_add.py"), Path("tests/test_sub.py")]
        prompt = build_implementation_prompt(paths)
        assert "test_add.py" in prompt
        assert "test_sub.py" in prompt

    def test_empty_paths_returns_no_changes(self):
        """Test that empty paths returns a no-changes message."""
        prompt = build_implementation_prompt([])
        assert "No generated tests" in prompt

    def test_with_plan_path(self):
        """Test that plan_path is included in the prompt."""
        paths = [Path("tests/test_add.py")]
        prompt = build_implementation_prompt(paths, plan_path=Path("plan.md"))
        assert "plan.md" in prompt

    def test_with_error_feedback(self):
        """Test that error feedback is included in the prompt."""
        paths = [Path("tests/test_add.py")]
        prompt = build_implementation_prompt(
            paths, error_feedback="FAILED test_add - assert 0 == 3"
        )
        assert "PREVIOUS ATTEMPT FAILED" in prompt
        assert "assert 0 == 3" in prompt

    def test_backward_compatible(self):
        """Test that calling with only test_paths still works."""
        paths = [Path("tests/test_add.py")]
        prompt = build_implementation_prompt(paths)
        assert "Implement production code" in prompt
        assert "test_add.py" in prompt

    def test_mentions_hidden_evaluations(self):
        """Test that prompt warns about hidden eval checks."""
        paths = [Path("tests/test_add.py")]
        prompt = build_implementation_prompt(paths)
        assert "hidden evaluations" in prompt.lower()
