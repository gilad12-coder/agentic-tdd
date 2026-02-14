"""Tests for the orchestrator loop."""

from unittest.mock import patch

from orchestrator.models import (
    CLIResult,
    ConstraintSet,
    FunctionProgress,
    FunctionStatus,
    ParsedSpec,
    SessionState,
    TaskConstraints,
    TestCritique,
)
from orchestrator.loop import (
    generate_tests,
    print_critique_report,
    process_function,
    prompt_user_review,
    run_critique,
    run_implementation,
)
from orchestrator.config import Config

MOCK_TEST_CODE = "def test_add():\n    assert add(1, 2) == 3"
MOCK_CRITIQUE_JSON = (
    '{"exploit_vectors": ["hardcode"], '
    '"missing_edge_cases": ["negative"], '
    '"suggested_counter_tests": ["test_neg"]}'
)


def _make_spec():
    return ParsedSpec(
        name="add",
        description="Add two numbers",
        examples=[{"input": "(1, 2)", "output": "3"}],
        signature="(a: int, b: int) -> int",
    )


def _make_constraints():
    return TaskConstraints(
        primary=ConstraintSet(max_cyclomatic_complexity=5),
        secondary=ConstraintSet(require_docstrings=True),
        target_files=["src/add.py"],
    )


def _make_config():
    return Config()


# --- generate_tests ---


class TestGenerateTests:
    @patch("orchestrator.loop.run_cli_agent")
    def test_generate_tests_calls_cli_agent_with_prompt(self, mock_run):
        mock_run.return_value = CLIResult(
            stdout=f"```python\n{MOCK_TEST_CODE}\n```",
            stderr="",
            exit_code=0,
        )
        result = generate_tests(_make_spec(), _make_constraints(), _make_config())
        mock_run.assert_called_once()
        prompt_arg = mock_run.call_args[0][0]
        assert "add" in prompt_arg
        assert "pytest" in prompt_arg

    @patch("orchestrator.loop.run_cli_agent")
    def test_generate_tests_extracts_python(self, mock_run):
        mock_run.return_value = CLIResult(
            stdout=f"Here is the code:\n```python\n{MOCK_TEST_CODE}\n```\nDone.",
            stderr="",
            exit_code=0,
        )
        result = generate_tests(_make_spec(), _make_constraints(), _make_config())
        assert "def test_add" in result
        assert "assert add(1, 2) == 3" in result


# --- run_critique ---


class TestRunCritique:
    @patch("orchestrator.loop.run_cli_agent")
    def test_run_critique_calls_cli_agent(self, mock_run):
        mock_run.return_value = CLIResult(
            stdout=MOCK_CRITIQUE_JSON,
            stderr="",
            exit_code=0,
        )
        run_critique(MOCK_TEST_CODE, _make_spec(), _make_config())
        mock_run.assert_called_once()
        prompt_arg = mock_run.call_args[0][0]
        assert "red-team" in prompt_arg.lower() or "critic" in prompt_arg.lower()

    @patch("orchestrator.loop.run_cli_agent")
    def test_run_critique_parses_json_response(self, mock_run):
        mock_run.return_value = CLIResult(
            stdout=MOCK_CRITIQUE_JSON,
            stderr="",
            exit_code=0,
        )
        critique = run_critique(MOCK_TEST_CODE, _make_spec(), _make_config())
        assert isinstance(critique, TestCritique)
        assert critique.exploit_vectors == ["hardcode"]


# --- process_function ---


class TestProcessFunction:
    @patch("orchestrator.loop.run_cli_agent")
    @patch("orchestrator.loop.prompt_user_review", return_value=(True, MOCK_TEST_CODE))
    def test_process_function_approve_flow(self, mock_review, mock_run):
        mock_run.side_effect = [
            CLIResult(
                stdout=f"```python\n{MOCK_TEST_CODE}\n```",
                stderr="",
                exit_code=0,
            ),
            CLIResult(stdout=MOCK_CRITIQUE_JSON, stderr="", exit_code=0),
        ]
        progress = process_function(
            "add", _make_spec(), _make_constraints(), _make_config()
        )
        assert progress.status == FunctionStatus.done
        assert progress.test_source is not None
        assert progress.critique is not None

    @patch("orchestrator.loop.run_cli_agent")
    @patch(
        "orchestrator.loop.prompt_user_review",
        side_effect=[(False, ""), (True, MOCK_TEST_CODE)],
    )
    def test_process_function_reject_then_approve(self, mock_review, mock_run):
        mock_run.side_effect = [
            CLIResult(
                stdout=f"```python\n{MOCK_TEST_CODE}\n```",
                stderr="",
                exit_code=0,
            ),
            CLIResult(
                stdout=f"```python\n{MOCK_TEST_CODE}\n```",
                stderr="",
                exit_code=0,
            ),
            CLIResult(stdout=MOCK_CRITIQUE_JSON, stderr="", exit_code=0),
        ]
        progress = process_function(
            "add", _make_spec(), _make_constraints(), _make_config()
        )
        assert progress.status == FunctionStatus.done
        assert mock_run.call_count == 3


# --- print_critique_report ---


class TestPrintCritiqueReport:
    def test_print_critique_report_outputs_all_sections(self, capsys):
        critique = TestCritique(
            exploit_vectors=["hardcode return"],
            missing_edge_cases=["empty input"],
            suggested_counter_tests=["def test_empty(): ..."],
        )
        print_critique_report(critique)
        output = capsys.readouterr().out
        assert "hardcode return" in output
        assert "empty input" in output
        assert "test_empty" in output


# --- run_implementation ---


class TestRunImplementation:
    @patch("orchestrator.loop.subprocess.run")
    def test_run_implementation_writes_test_files(self, mock_subprocess, tmp_path):
        mock_subprocess.return_value = type(
            "Result", (), {"returncode": 0, "stdout": "", "stderr": ""}
        )()
        state = SessionState(
            function_progress=[
                FunctionProgress(
                    name="add",
                    status=FunctionStatus.done,
                    test_source="def test_add(): assert add(1, 2) == 3",
                ),
            ]
        )
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        run_implementation(state, _make_config(), test_dir=test_dir)
        test_file = test_dir / "test_add.py"
        assert test_file.exists()
        assert "def test_add" in test_file.read_text()

    @patch("orchestrator.loop.subprocess.run")
    def test_run_implementation_runs_agent_and_verifies(self, mock_subprocess, tmp_path):
        mock_subprocess.return_value = type(
            "Result", (), {"returncode": 0, "stdout": "", "stderr": ""}
        )()
        state = SessionState(
            function_progress=[
                FunctionProgress(
                    name="add",
                    status=FunctionStatus.done,
                    test_source="def test_add(): pass",
                ),
            ]
        )
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        result = run_implementation(state, _make_config(), test_dir=test_dir)
        assert result is True
        # At least 2 subprocess calls: implementing agent + pytest
        assert mock_subprocess.call_count >= 2


# --- prompt_user_review (edit flow) ---


class TestPromptUserReviewEdit:
    @patch("orchestrator.loop._open_in_editor")
    @patch("orchestrator.loop.display_test_source")
    @patch("builtins.input")
    def test_prompt_user_review_edit_then_approve(
        self, mock_input, mock_display, mock_editor
    ):
        mock_input.side_effect = ["e", "a"]
        mock_editor.return_value = "edited code"
        approved, source = prompt_user_review("original code")
        assert approved is True
        assert source == "edited code"

    @patch("orchestrator.loop._open_in_editor")
    @patch("orchestrator.loop.display_test_source")
    @patch("builtins.input")
    def test_prompt_user_review_edit_failure_continues(
        self, mock_input, mock_display, mock_editor
    ):
        mock_input.side_effect = ["e", "a"]
        mock_editor.return_value = None
        approved, source = prompt_user_review("original code")
        assert approved is True
        assert source == "original code"


# --- generate_tests (error handling) ---


class TestGenerateTestsErrorHandling:
    @patch("orchestrator.loop.display_error")
    @patch("orchestrator.loop.run_cli_agent")
    def test_generate_tests_agent_failure_returns_empty(
        self, mock_run, mock_display_error
    ):
        mock_run.return_value = CLIResult(
            stdout="", stderr="Agent crashed", exit_code=-1
        )
        result = generate_tests(_make_spec(), _make_constraints(), _make_config())
        assert result == ""
        mock_display_error.assert_called_once()


# --- process_function (exploit integration) ---


class TestProcessFunctionExploit:
    @patch("orchestrator.loop.run_exploit_check", return_value=(True, "def add(a,b): return 3"))
    @patch("orchestrator.loop.run_cli_agent")
    @patch("orchestrator.loop.prompt_user_review", return_value=(True, MOCK_TEST_CODE))
    def test_process_function_sets_exploit_fields(
        self, mock_review, mock_run, mock_exploit
    ):
        mock_run.side_effect = [
            CLIResult(
                stdout=f"```python\n{MOCK_TEST_CODE}\n```",
                stderr="",
                exit_code=0,
            ),
            CLIResult(stdout=MOCK_CRITIQUE_JSON, stderr="", exit_code=0),
        ]
        progress = process_function(
            "add", _make_spec(), _make_constraints(), _make_config()
        )
        assert progress.critique is not None
        assert progress.critique.exploit_passed is True
        assert progress.critique.exploit_code == "def add(a,b): return 3"

    @patch("orchestrator.loop.run_exploit_check", return_value=(False, ""))
    @patch("orchestrator.loop.run_cli_agent")
    @patch("orchestrator.loop.prompt_user_review", return_value=(True, MOCK_TEST_CODE))
    def test_process_function_exploit_failure_still_completes(
        self, mock_review, mock_run, mock_exploit
    ):
        mock_run.side_effect = [
            CLIResult(
                stdout=f"```python\n{MOCK_TEST_CODE}\n```",
                stderr="",
                exit_code=0,
            ),
            CLIResult(stdout=MOCK_CRITIQUE_JSON, stderr="", exit_code=0),
        ]
        progress = process_function(
            "add", _make_spec(), _make_constraints(), _make_config()
        )
        assert progress.status == FunctionStatus.done
        assert progress.critique is not None
        assert progress.critique.exploit_passed is False
