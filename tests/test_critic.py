import json
from unittest.mock import patch

import pytest

from orchestrator.config import Config
from orchestrator.critic import (
    _strip_local_imports,
    build_critic_prompt,
    parse_critique,
    run_exploit_check,
)
from orchestrator.models import CLIResult, ConstraintSet, TaskConstraints, TestCritique


SAMPLE_TEST_SOURCE = '''\
import pytest

def test_add_positive():
    assert add(1, 2) == 3

def test_add_zero():
    assert add(0, 0) == 0

def test_add_negative():
    assert add(-1, -1) == -2
'''


# --- Unit tests: prompt construction and parsing ---


class TestBuildCriticPrompt:
    """Tests for build_critic_prompt."""

    def test_build_critic_prompt_contains_source_and_adversarial_words(self, minimal_spec):
        """Test that build_critic_prompt includes test source and adversarial language.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
        """
        prompt = build_critic_prompt(SAMPLE_TEST_SOURCE, minimal_spec)
        assert isinstance(prompt, str)
        assert "test_add_positive" in prompt
        assert "exploit" in prompt.lower() or "game" in prompt.lower() or "cheat" in prompt.lower()

    def test_build_critic_prompt_requests_json(self, minimal_spec):
        """Test that build_critic_prompt requests JSON output.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
        """
        prompt = build_critic_prompt(SAMPLE_TEST_SOURCE, minimal_spec)
        assert "json" in prompt.lower()

    def test_build_critic_prompt_includes_guidance(self, minimal_spec):
        """Test that build_critic_prompt includes constraint guidance.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
        """
        constraints = TaskConstraints(
            primary=ConstraintSet(),
            secondary=ConstraintSet(),
            target_files=[],
            guidance=["Prefer early returns.", "Avoid inline comments."],
        )
        prompt = build_critic_prompt(SAMPLE_TEST_SOURCE, minimal_spec, constraints)
        assert "Prefer early returns." in prompt
        assert "Avoid inline comments." in prompt

    def test_build_critic_prompt_includes_constraints(self, minimal_spec):
        """Test that build_critic_prompt includes constraint values.

        Args:
            minimal_spec: Minimal ParsedSpec fixture.
        """
        constraints = TaskConstraints(
            primary=ConstraintSet(max_cyclomatic_complexity=5, max_lines_per_function=30),
            secondary=ConstraintSet(),
            target_files=[],
        )
        prompt = build_critic_prompt(SAMPLE_TEST_SOURCE, minimal_spec, constraints)
        assert "5" in prompt
        assert "30" in prompt


class TestParseCritique:
    """Tests for parse_critique."""

    def test_parse_critique_valid_json(self):
        """Test that parse_critique parses valid JSON into a TestCritique."""
        raw_json = json.dumps({
            "exploit_vectors": ["hardcode return values for known inputs"],
            "missing_edge_cases": ["large integers", "type errors"],
            "suggested_counter_tests": [
                "def test_add_large(): assert add(10**18, 10**18) == 2 * 10**18"
            ],
        })
        critique = parse_critique(raw_json)
        assert isinstance(critique, TestCritique)
        assert len(critique.exploit_vectors) == 1
        assert len(critique.missing_edge_cases) == 2
        assert len(critique.suggested_counter_tests) == 1

    def test_parse_critique_invalid_json(self):
        """Test that parse_critique raises on invalid JSON."""
        with pytest.raises((ValueError, json.JSONDecodeError)):
            parse_critique("this is not valid json at all")

    def test_parse_critique_embedded_json_in_text(self):
        """Test that parse_critique extracts JSON embedded in surrounding text."""
        raw = (
            "Here is my analysis:\n"
            '{"exploit_vectors": ["cheat"], '
            '"missing_edge_cases": [], '
            '"suggested_counter_tests": []}\n'
            "End of analysis."
        )
        critique = parse_critique(raw)
        assert isinstance(critique, TestCritique)
        assert critique.exploit_vectors == ["cheat"]

    def test_parse_critique_extra_fields_ignored(self):
        """Test that parse_critique ignores extra JSON fields."""
        raw_json = json.dumps({
            "exploit_vectors": ["cheat"],
            "missing_edge_cases": ["edge"],
            "suggested_counter_tests": ["def test_x(): pass"],
            "reasoning": "This is extra commentary from the LLM",
        })
        critique = parse_critique(raw_json)
        assert isinstance(critique, TestCritique)
        assert not hasattr(critique, "reasoning") or critique.__dict__.get("reasoning") is None

    def test_parse_critique_malformed_json_with_unescaped_braces(self):
        """Test that parse_critique handles JSON with unescaped braces in strings."""
        raw = (
            '{"exploit_vectors": ["hardcoded lookup table {0:1, 5:120}"], '
            '"missing_edge_cases": ["negative input"], '
            '"suggested_counter_tests": ["test random values"]}'
        )
        critique = parse_critique(raw)
        assert isinstance(critique, TestCritique)
        assert len(critique.exploit_vectors) == 1
        assert "lookup table" in critique.exploit_vectors[0]
        assert critique.missing_edge_cases == ["negative input"]


# --- run_exploit_check ---


EXPLOIT_CODE = "def add(a, b):\n    return {(1,2): 3, (0,0): 0}.get((a,b), 0)"


class TestRunExploitCheck:
    """Tests for run_exploit_check."""
    @patch("orchestrator.critic.subprocess.run")
    @patch("orchestrator.critic.run_cli_agent")
    def test_run_exploit_check_passes_returns_true(
        self, mock_agent, mock_pytest, minimal_spec
    ):
        """Test that run_exploit_check returns True when exploit passes tests.

        Args:
            mock_agent: Mocked run_cli_agent.
            mock_pytest: Mocked subprocess.run.
            minimal_spec: Minimal ParsedSpec fixture.
        """
        mock_agent.return_value = CLIResult(
            stdout=f"```python\n{EXPLOIT_CODE}\n```",
            stderr="",
            exit_code=0,
        )
        mock_pytest.return_value = type(
            "Result", (), {"returncode": 0, "stdout": "", "stderr": ""}
        )()
        passed, code = run_exploit_check(
            SAMPLE_TEST_SOURCE, minimal_spec, Config()
        )
        assert passed is True
        assert "add" in code

    @patch("orchestrator.critic.subprocess.run")
    @patch("orchestrator.critic.run_cli_agent")
    def test_run_exploit_check_fails_returns_false(
        self, mock_agent, mock_pytest, minimal_spec
    ):
        """Test that run_exploit_check returns False when exploit fails tests.

        Args:
            mock_agent: Mocked run_cli_agent.
            mock_pytest: Mocked subprocess.run.
            minimal_spec: Minimal ParsedSpec fixture.
        """
        mock_agent.return_value = CLIResult(
            stdout=f"```python\n{EXPLOIT_CODE}\n```",
            stderr="",
            exit_code=0,
        )
        mock_pytest.return_value = type(
            "Result", (), {"returncode": 1, "stdout": "", "stderr": "FAILED"}
        )()
        passed, code = run_exploit_check(
            SAMPLE_TEST_SOURCE, minimal_spec, Config()
        )
        assert passed is False
        assert code

    @patch("orchestrator.critic.run_cli_agent")
    def test_run_exploit_check_agent_failure_returns_false(
        self, mock_agent, minimal_spec
    ):
        """Test that run_exploit_check returns False when the agent crashes.

        Args:
            mock_agent: Mocked run_cli_agent.
            minimal_spec: Minimal ParsedSpec fixture.
        """
        mock_agent.return_value = CLIResult(
            stdout="", stderr="Agent crashed", exit_code=-1
        )
        passed, code = run_exploit_check(
            SAMPLE_TEST_SOURCE, minimal_spec, Config()
        )
        assert passed is False
        assert code == ""


class TestStripLocalImports:
    """Tests for _strip_local_imports."""

    def test_strips_local_module_import(self):
        """Test that a from-import of a local module is stripped."""
        source = "from merge_intervals import merge_intervals\n"
        result = _strip_local_imports(source)
        assert "merge_intervals" not in result

    def test_keeps_pytest_import(self):
        """Test that a from-import of pytest is kept."""
        source = "from pytest import raises\n"
        result = _strip_local_imports(source)
        assert "from pytest import raises" in result

    def test_keeps_collections_import(self):
        """Test that a from-import of collections is kept."""
        source = "from collections import defaultdict\n"
        result = _strip_local_imports(source)
        assert "from collections import defaultdict" in result

    def test_keeps_bare_import(self):
        """Test that a bare import statement is kept."""
        source = "import pytest\n"
        result = _strip_local_imports(source)
        assert "import pytest" in result

    def test_keeps_dotted_package(self):
        """Test that a from-import of a dotted package is kept."""
        source = "from unittest.mock import patch\n"
        result = _strip_local_imports(source)
        assert "from unittest.mock import patch" in result

    def test_mixed_source(self):
        """Test that only local imports are stripped from mixed source."""
        source = (
            "from pytest import raises\n"
            "from merge_intervals import merge_intervals\n"
            "from collections import defaultdict\n"
            "\n"
            "def test_example():\n"
            "    pass\n"
        )
        result = _strip_local_imports(source)
        assert "from pytest import raises" in result
        assert "from collections import defaultdict" in result
        assert "merge_intervals" not in result
        assert "def test_example():" in result
