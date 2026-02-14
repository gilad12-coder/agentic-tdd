import json
from unittest.mock import patch

import pytest

from orchestrator.config import Config
from orchestrator.critic import build_critic_prompt, parse_critique, run_exploit_check
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
    def test_build_critic_prompt_contains_source_and_adversarial_words(self, minimal_spec):
        prompt = build_critic_prompt(SAMPLE_TEST_SOURCE, minimal_spec)
        assert isinstance(prompt, str)
        assert "test_add_positive" in prompt
        assert "exploit" in prompt.lower() or "game" in prompt.lower() or "cheat" in prompt.lower()

    def test_build_critic_prompt_requests_json(self, minimal_spec):
        prompt = build_critic_prompt(SAMPLE_TEST_SOURCE, minimal_spec)
        assert "json" in prompt.lower()

    def test_build_critic_prompt_includes_guidance(self, minimal_spec):
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
        constraints = TaskConstraints(
            primary=ConstraintSet(max_cyclomatic_complexity=5, max_lines_per_function=30),
            secondary=ConstraintSet(),
            target_files=[],
        )
        prompt = build_critic_prompt(SAMPLE_TEST_SOURCE, minimal_spec, constraints)
        assert "5" in prompt
        assert "30" in prompt


class TestParseCritique:
    def test_parse_critique_valid_json(self):
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
        with pytest.raises((ValueError, json.JSONDecodeError)):
            parse_critique("this is not valid json at all")

    def test_parse_critique_embedded_json_in_text(self):
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
        raw_json = json.dumps({
            "exploit_vectors": ["cheat"],
            "missing_edge_cases": ["edge"],
            "suggested_counter_tests": ["def test_x(): pass"],
            "reasoning": "This is extra commentary from the LLM",
        })
        critique = parse_critique(raw_json)
        assert isinstance(critique, TestCritique)
        assert not hasattr(critique, "reasoning") or critique.__dict__.get("reasoning") is None


# --- run_exploit_check ---


EXPLOIT_CODE = "def add(a, b):\n    return {(1,2): 3, (0,0): 0}.get((a,b), 0)"


class TestRunExploitCheck:
    @patch("orchestrator.critic.subprocess.run")
    @patch("orchestrator.critic.run_cli_agent")
    def test_run_exploit_check_passes_returns_true(
        self, mock_agent, mock_pytest, minimal_spec
    ):
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
        mock_agent.return_value = CLIResult(
            stdout="", stderr="Agent crashed", exit_code=-1
        )
        passed, code = run_exploit_check(
            SAMPLE_TEST_SOURCE, minimal_spec, Config()
        )
        assert passed is False
        assert code == ""
