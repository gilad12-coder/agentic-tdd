"""Integration tests that call a real LLM via Claude CLI.

Run with: pytest tests/test_llm_integration.py -m llm -v
These are excluded from normal runs via: pytest -m 'not llm'
"""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from orchestrator.cli_runner import run_cli_agent
from orchestrator.config import Config
from orchestrator.critic import parse_critique
from orchestrator.loop import (
    process_function,
    run_session,
    validate_test_constraints,
    validate_test_syntax,
)
from orchestrator.models import (
    ConstraintSet,
    FunctionStatus,
    ParsedSpec,
    TaskConstraints,
    TestCritique,
)
from orchestrator.prompts import build_critic_prompt, build_generation_prompt
from orchestrator.test_generator import extract_python_from_response


def _skip_if_no_claude():
    """Skip test if claude CLI is not available."""
    if shutil.which("claude") is None:
        pytest.skip("claude CLI not found")


def _spec():
    """Create a simple ParsedSpec for integration testing.

    Returns:
        ParsedSpec for a factorial function.
    """
    return ParsedSpec(
        name="factorial",
        description="Compute the factorial of a non-negative integer.",
        examples=[
            {"input": "(0)", "output": "1"},
            {"input": "(5)", "output": "120"},
        ],
        signature="(n: int) -> int",
    )


def _constraints():
    """Create constraints for integration testing.

    Returns:
        TaskConstraints with docstring and complexity requirements.
    """
    return TaskConstraints(
        primary=ConstraintSet(max_cyclomatic_complexity=10),
        secondary=ConstraintSet(require_docstrings=True),
        target_files=[],
    )


def _config():
    """Create a Config for integration testing.

    Returns:
        Config with default settings.
    """
    return Config()


# --- Component tests (each calls the LLM once in isolation) ---


@pytest.mark.llm
@pytest.mark.timeout(120)
class TestLLMGeneration:
    """Test that the generation agent produces valid, constraint-compliant code."""

    def test_generate_returns_valid_python(self):
        """Test that LLM generation returns syntactically valid Python."""
        _skip_if_no_claude()
        spec = _spec()
        constraints = _constraints()
        config = _config()
        prompt = build_generation_prompt(spec, constraints)
        result = run_cli_agent(
            prompt,
            config.generation_agent,
            config.generation_model,
            config.max_budget_usd,
        )
        source = extract_python_from_response(result.stdout)
        assert source != "", "LLM returned no extractable Python"
        syntax_ok, errors = validate_test_syntax(source)
        assert syntax_ok, f"Generated code has syntax errors: {errors}"

    def test_generate_passes_constraints(self):
        """Test that LLM generation satisfies configured constraints."""
        _skip_if_no_claude()
        spec = _spec()
        constraints = _constraints()
        config = _config()
        prompt = build_generation_prompt(spec, constraints)
        result = run_cli_agent(
            prompt,
            config.generation_agent,
            config.generation_model,
            config.max_budget_usd,
        )
        source = extract_python_from_response(result.stdout)
        assert source != ""
        passed, violations = validate_test_constraints(source, constraints)
        # If first attempt fails, try with feedback (mirrors real loop)
        if not passed:
            prompt_retry = build_generation_prompt(
                spec, constraints, constraint_feedback=violations
            )
            result = run_cli_agent(
                prompt_retry,
                config.generation_agent,
                config.generation_model,
                config.max_budget_usd,
            )
            source = extract_python_from_response(result.stdout)
            passed, violations = validate_test_constraints(source, constraints)
        assert passed, f"Generated code violates constraints:\n{violations}"


@pytest.mark.llm
@pytest.mark.timeout(120)
class TestLLMCritique:
    """Test that the critic agent returns parseable JSON with flat string lists."""

    def test_critique_parses_to_model(self):
        """Test that real critic output parses into TestCritique."""
        _skip_if_no_claude()
        spec = _spec()
        constraints = _constraints()
        config = _config()
        test_source = (
            'from factorial import factorial\n\n\n'
            'class TestFactorial:\n'
            '    """Tests for factorial."""\n\n'
            '    def test_zero(self):\n'
            '        """Test factorial of zero."""\n'
            '        assert factorial(0) == 1\n\n'
            '    def test_five(self):\n'
            '        """Test factorial of five."""\n'
            '        assert factorial(5) == 120\n'
        )
        prompt = build_critic_prompt(test_source, spec, constraints)
        result = run_cli_agent(
            prompt,
            config.critic_agent,
            config.critic_model,
            config.max_budget_usd,
        )
        critique = parse_critique(result.stdout)
        assert isinstance(critique, TestCritique)
        assert isinstance(critique.exploit_vectors, list)
        # Every item must be a string, not a dict
        for item in critique.exploit_vectors:
            assert isinstance(item, str), f"Expected str, got {type(item)}: {item}"
        for item in critique.missing_edge_cases:
            assert isinstance(item, str), f"Expected str, got {type(item)}: {item}"
        for item in critique.suggested_counter_tests:
            assert isinstance(item, str), f"Expected str, got {type(item)}: {item}"


# --- E2E test (full flow with real LLM, only mock user review) ---


@pytest.mark.llm
@pytest.mark.timeout(300)
class TestLLMProcessFunction:
    """Full process_function flow with real LLM calls."""

    @patch("orchestrator.loop.prompt_critique_review", return_value=True)
    @patch("orchestrator.loop.prompt_user_review")
    def test_full_flow(self, mock_review, _):
        """Test the full generate → validate → critique flow with real LLM.

        Args:
            mock_review: Mocked prompt_user_review to auto-approve.
            _: Mocked prompt_critique_review (auto-accept).
        """
        _skip_if_no_claude()
        mock_review.side_effect = lambda source, **kwargs: (True, source)
        spec = _spec()
        constraints = _constraints()
        config = _config()
        progress = process_function("factorial", spec, constraints, config)
        assert progress.status == FunctionStatus.done
        assert progress.test_source is not None
        assert len(progress.test_source) > 0
        assert progress.critique is not None
        assert isinstance(progress.critique.exploit_vectors, list)


# --- Full run_session E2E (spec YAML → completed session) ---


_E2E_SPEC = {
    "name": "math_utils",
    "description": "Simple math utility functions.",
    "constraint_profile": "default",
    "target_files": ["math_utils.py"],
    "functions": [
        {
            "name": "factorial",
            "description": (
                "Compute the factorial of a non-negative integer. "
                "factorial(0) returns 1. Raises ValueError for negative input."
            ),
            "signature": "(n: int) -> int",
            "examples": [
                {"input": "(0)", "output": "1"},
                {"input": "(5)", "output": "120"},
            ],
        },
        {
            "name": "fibonacci",
            "description": (
                "Return the nth Fibonacci number (0-indexed). "
                "fibonacci(0) returns 0, fibonacci(1) returns 1."
            ),
            "signature": "(n: int) -> int",
            "examples": [
                {"input": "(0)", "output": "0"},
                {"input": "(6)", "output": "8"},
            ],
        },
    ],
}


@pytest.mark.llm
@pytest.mark.timeout(600)
class TestLLMRunSession:
    """Full run_session flow: spec YAML → profiles → all functions → session."""

    @patch("orchestrator.loop.prompt_critique_review", return_value=True)
    @patch("orchestrator.loop.prompt_user_review")
    def test_run_session_completes_all_functions(self, mock_review, _, tmp_path):
        """Test that run_session processes every function from a spec file.

        Args:
            mock_review: Mocked prompt_user_review to auto-approve.
            _: Mocked prompt_critique_review (auto-accept).
            tmp_path: Pytest tmp_path fixture for temp files.
        """
        _skip_if_no_claude()
        mock_review.side_effect = lambda source, **kwargs: (True, source)

        # Write spec YAML
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(yaml.dump(_E2E_SPEC), encoding="utf-8")

        # Use the real profiles file
        profiles_path = Path(__file__).parent.parent / "constraints" / "profiles.yaml"
        session_path = tmp_path / ".session.json"

        state = run_session(spec_path, profiles_path, session_path)

        # All functions should be done
        assert len(state.function_progress) == 2
        for progress in state.function_progress:
            assert progress.status == FunctionStatus.done, (
                f"{progress.name} not done: {progress.status}"
            )
            assert progress.test_source is not None
            assert len(progress.test_source) > 0
            assert progress.critique is not None

        # Session file should exist
        assert session_path.exists()
