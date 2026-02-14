"""Tests for the orchestrator loop."""

from pathlib import Path
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
    prompt_critique_review,
    prompt_user_review,
    run_critique,
    run_implementation,
    run_session,
    validate_test_constraints,
    validate_test_syntax,
)
from orchestrator.config import Config

MOCK_TEST_CODE = 'def test_add():\n    """Test add."""\n    assert add(1, 2) == 3'
MOCK_CRITIQUE_JSON = (
    '{"exploit_vectors": ["hardcode"], '
    '"missing_edge_cases": ["negative"], '
    '"suggested_counter_tests": ["test_neg"]}'
)


def _make_spec():
    """Create a minimal ParsedSpec for testing.

    Returns:
        ParsedSpec with name "add" and basic examples.
    """
    return ParsedSpec(
        name="add",
        description="Add two numbers",
        examples=[{"input": "(1, 2)", "output": "3"}],
        signature="(a: int, b: int) -> int",
    )


def _make_constraints():
    """Create minimal TaskConstraints for testing.

    Returns:
        TaskConstraints with basic primary and secondary constraints.
    """
    return TaskConstraints(
        primary=ConstraintSet(max_cyclomatic_complexity=5),
        secondary=ConstraintSet(require_docstrings=True),
        target_files=["src/add.py"],
    )


def _make_config():
    """Create a default Config for testing.

    Returns:
        Config with default settings.
    """
    return Config()


# --- generate_tests ---


class TestGenerateTests:
    """Tests for generate_tests."""

    @patch("orchestrator.loop.run_cli_agent")
    def test_generate_tests_calls_cli_agent_with_prompt(self, mock_run):
        """Test that generate_tests calls the CLI agent with the correct prompt.

        Args:
            mock_run: Mocked run_cli_agent.
        """
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
        """Test that generate_tests extracts Python code from the response.

        Args:
            mock_run: Mocked run_cli_agent.
        """
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
    """Tests for run_critique."""

    @patch("orchestrator.loop.run_cli_agent")
    def test_run_critique_calls_cli_agent(self, mock_run):
        """Test that run_critique calls the CLI agent with a critic prompt.

        Args:
            mock_run: Mocked run_cli_agent.
        """
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
        """Test that run_critique parses the JSON response into a TestCritique.

        Args:
            mock_run: Mocked run_cli_agent.
        """
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
    """Tests for process_function."""

    @patch("orchestrator.loop.prompt_critique_review", return_value=True)
    @patch("orchestrator.loop.run_cli_agent")
    @patch("orchestrator.loop.prompt_user_review", return_value=(True, MOCK_TEST_CODE))
    def test_process_function_approve_flow(self, mock_review, mock_run, _):
        """Test that process_function completes when user approves tests.

        Args:
            mock_review: Mocked prompt_user_review.
            mock_run: Mocked run_cli_agent.
            _: Mocked prompt_critique_review (auto-accept).
        """
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

    @patch("orchestrator.loop.prompt_critique_review", return_value=True)
    @patch("orchestrator.loop.run_cli_agent")
    @patch(
        "orchestrator.loop.prompt_user_review",
        side_effect=[(False, ""), (True, MOCK_TEST_CODE)],
    )
    def test_process_function_reject_then_approve(self, mock_review, mock_run, _):
        """Test that process_function retries after user rejection.

        Args:
            mock_review: Mocked prompt_user_review.
            mock_run: Mocked run_cli_agent.
            _: Mocked prompt_critique_review (auto-accept).
        """
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
    """Tests for print_critique_report."""

    def test_print_critique_report_outputs_all_sections(self, capsys):
        """Test that print_critique_report outputs all critique sections.

        Args:
            capsys: Pytest capsys fixture.
        """
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
    """Tests for run_implementation."""

    @patch("orchestrator.loop.subprocess.run")
    def test_run_implementation_writes_test_files(self, mock_subprocess, tmp_path):
        """Test that run_implementation writes test files to the test directory.

        Args:
            mock_subprocess: Mocked subprocess.run.
            tmp_path: Pytest tmp_path fixture.
        """
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
        """Test that run_implementation runs the agent and verifies with pytest.

        Args:
            mock_subprocess: Mocked subprocess.run.
            tmp_path: Pytest tmp_path fixture.
        """
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
    """Tests for prompt_user_review edit flow."""
    @patch("orchestrator.loop._open_in_editor")
    @patch("orchestrator.loop.display_test_source")
    @patch("builtins.input")
    def test_prompt_user_review_edit_then_approve(
        self, mock_input, mock_display, mock_editor
    ):
        """Test that user can edit then approve test source.

        Args:
            mock_input: Mocked builtins.input.
            mock_display: Mocked display_test_source.
            mock_editor: Mocked _open_in_editor.
        """
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
        """Test that edit failure falls back to original source.

        Args:
            mock_input: Mocked builtins.input.
            mock_display: Mocked display_test_source.
            mock_editor: Mocked _open_in_editor.
        """
        mock_input.side_effect = ["e", "a"]
        mock_editor.return_value = None
        approved, source = prompt_user_review("original code")
        assert approved is True
        assert source == "original code"


# --- generate_tests (error handling) ---


class TestGenerateTestsErrorHandling:
    """Tests for generate_tests error handling."""
    @patch("orchestrator.loop.display_error")
    @patch("orchestrator.loop.run_cli_agent")
    def test_generate_tests_agent_failure_returns_empty(
        self, mock_run, mock_display_error
    ):
        """Test that generate_tests returns empty string on agent failure.

        Args:
            mock_run: Mocked run_cli_agent.
            mock_display_error: Mocked display_error.
        """
        mock_run.return_value = CLIResult(
            stdout="", stderr="Agent crashed", exit_code=-1
        )
        result = generate_tests(_make_spec(), _make_constraints(), _make_config())
        assert result == ""
        mock_display_error.assert_called_once()


# --- process_function (exploit integration) ---


class TestProcessFunctionExploit:
    """Tests for process_function exploit integration."""
    @patch("orchestrator.loop.prompt_critique_review", return_value=True)
    @patch("orchestrator.loop.run_exploit_check", return_value=(True, "def add(a,b): return 3"))
    @patch("orchestrator.loop.run_cli_agent")
    @patch("orchestrator.loop.prompt_user_review", return_value=(True, MOCK_TEST_CODE))
    def test_process_function_sets_exploit_fields(
        self, mock_review, mock_run, mock_exploit, _
    ):
        """Test that process_function sets exploit fields on the critique.

        Args:
            mock_review: Mocked prompt_user_review.
            mock_run: Mocked run_cli_agent.
            mock_exploit: Mocked run_exploit_check.
            _: Mocked prompt_critique_review (auto-accept).
        """
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

    @patch("orchestrator.loop.prompt_critique_review", return_value=True)
    @patch("orchestrator.loop.run_exploit_check", return_value=(False, ""))
    @patch("orchestrator.loop.run_cli_agent")
    @patch("orchestrator.loop.prompt_user_review", return_value=(True, MOCK_TEST_CODE))
    def test_process_function_exploit_failure_still_completes(
        self, mock_review, mock_run, mock_exploit, _
    ):
        """Test that process_function completes even when exploit check fails.

        Args:
            mock_review: Mocked prompt_user_review.
            mock_run: Mocked run_cli_agent.
            mock_exploit: Mocked run_exploit_check.
            _: Mocked prompt_critique_review (auto-accept).
        """
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


class TestValidateTestSyntax:
    """Tests for validate_test_syntax."""

    def test_valid_test_passes(self):
        """Test that valid test source passes syntax validation."""
        source = "def test_example():\n    assert 1 + 1 == 2\n"
        passed, errors = validate_test_syntax(source)
        assert passed is True
        assert errors == ""

    def test_syntax_error_fails(self):
        """Test that source with syntax errors fails validation."""
        source = "def test_broken(\n    assert 1 == 1\n"
        passed, errors = validate_test_syntax(source)
        assert passed is False
        assert errors != ""

    def test_import_of_nonexistent_module_passes(self):
        """Test that imports of nonexistent modules pass syntax validation.

        In TDD, tests import modules that don't exist yet.
        Syntax validation should not reject these.
        """
        source = "from nonexistent_module import foo\ndef test_it():\n    assert foo() == 1\n"
        passed, errors = validate_test_syntax(source)
        assert passed is True
        assert errors == ""

    def test_valid_source_with_import_passes(self):
        """Test that valid source with standard imports passes validation."""
        source = "import os\ndef test_path():\n    assert os.sep in ('/', '\\\\')\n"
        passed, errors = validate_test_syntax(source)
        assert passed is True


class TestValidateTestConstraints:
    """Tests for validate_test_constraints."""

    def test_passing_constraints(self):
        """Test that compliant source passes constraint validation."""
        source = (
            '"""Module docstring."""\n'
            'def test_add():\n'
            '    """Test addition."""\n'
            '    assert 1 + 1 == 2\n'
        )
        constraints = _make_constraints()
        passed, errors = validate_test_constraints(source, constraints)
        assert passed is True
        assert errors == ""

    def test_missing_docstring_fails(self):
        """Test that missing docstrings fail when require_docstrings is set."""
        source = "def test_add():\n    assert 1 + 1 == 2\n"
        constraints = TaskConstraints(
            primary=ConstraintSet(),
            secondary=ConstraintSet(require_docstrings=True),
            target_files=[],
        )
        passed, errors = validate_test_constraints(source, constraints)
        assert passed is False
        assert "docstring" in errors.lower()

    def test_complexity_violation_fails(self):
        """Test that high complexity fails when max_cyclomatic_complexity is set."""
        # Build source with high cyclomatic complexity via many branches
        branches = "\n".join(
            f"    if x == {i}: return {i}" for i in range(12)
        )
        source = f'def test_complex(x):\n    """Docstring."""\n{branches}\n'
        constraints = TaskConstraints(
            primary=ConstraintSet(max_cyclomatic_complexity=3),
            secondary=ConstraintSet(),
            target_files=[],
        )
        passed, errors = validate_test_constraints(source, constraints)
        assert passed is False
        assert "complexity" in errors.lower()


# --- end-to-end ---


# Realistic test code that passes constraints (has docstrings)
_E2E_TEST_CODE = (
    '"""Tests for add."""\n\n'
    'from add import add\n\n\n'
    'class TestAdd:\n'
    '    """Tests for the add function."""\n\n'
    '    def test_basic(self):\n'
    '        """Test basic addition."""\n'
    '        assert add(1, 2) == 3\n\n'
    '    def test_zero(self):\n'
    '        """Test adding zero."""\n'
    '        assert add(0, 0) == 0\n'
)

# Realistic critique JSON with flat string lists (matching expected schema)
_E2E_CRITIQUE_JSON = (
    '{"exploit_vectors": ["hardcode return 3 for known inputs"], '
    '"missing_edge_cases": ["negative numbers", "large values"], '
    '"suggested_counter_tests": ["test_negative", "test_large"]}'
)


class TestEndToEnd:
    """End-to-end test exercising the full process_function flow."""

    @patch("orchestrator.loop.prompt_critique_review", return_value=True)
    @patch("orchestrator.loop.run_exploit_check", return_value=(False, ""))
    @patch("orchestrator.loop.run_cli_agent")
    @patch("orchestrator.loop.prompt_user_review")
    def test_full_flow_generate_validate_critique(
        self, mock_review, mock_run, mock_exploit, _
    ):
        """Test the full flow: generate, validate constraints, critique.

        Args:
            mock_review: Mocked prompt_user_review.
            mock_run: Mocked run_cli_agent.
            mock_exploit: Mocked run_exploit_check.
            _: Mocked prompt_critique_review (auto-accept).
        """
        mock_review.return_value = (True, _E2E_TEST_CODE)
        mock_run.side_effect = [
            # Generation agent returns test code
            CLIResult(
                stdout=f"```python\n{_E2E_TEST_CODE}\n```",
                stderr="",
                exit_code=0,
            ),
            # Critic agent returns JSON
            CLIResult(stdout=_E2E_CRITIQUE_JSON, stderr="", exit_code=0),
        ]
        progress = process_function(
            "add", _make_spec(), _make_constraints(), _make_config()
        )
        assert progress.status == FunctionStatus.done
        assert progress.test_source == _E2E_TEST_CODE
        assert progress.critique is not None
        assert progress.critique.exploit_vectors == [
            "hardcode return 3 for known inputs"
        ]
        assert progress.critique.missing_edge_cases == [
            "negative numbers",
            "large values",
        ]

    @patch("orchestrator.loop.prompt_critique_review", return_value=True)
    @patch("orchestrator.loop.run_exploit_check", return_value=(False, ""))
    @patch("orchestrator.loop.run_cli_agent")
    @patch("orchestrator.loop.prompt_user_review")
    def test_constraint_feedback_loop(self, mock_review, mock_run, mock_exploit, _):
        """Test that constraint violations trigger regeneration with feedback.

        Args:
            mock_review: Mocked prompt_user_review.
            mock_run: Mocked run_cli_agent.
            mock_exploit: Mocked run_exploit_check.
            _: Mocked prompt_critique_review (auto-accept).
        """
        bad_code = "def test_add():\n    assert 1 + 1 == 2\n"
        mock_review.return_value = (True, _E2E_TEST_CODE)
        mock_run.side_effect = [
            # First attempt: no docstrings, will fail constraint check
            CLIResult(
                stdout=f"```python\n{bad_code}\n```",
                stderr="",
                exit_code=0,
            ),
            # Second attempt: with docstrings, passes constraints
            CLIResult(
                stdout=f"```python\n{_E2E_TEST_CODE}\n```",
                stderr="",
                exit_code=0,
            ),
            # Critic
            CLIResult(stdout=_E2E_CRITIQUE_JSON, stderr="", exit_code=0),
        ]
        progress = process_function(
            "add", _make_spec(), _make_constraints(), _make_config()
        )
        assert progress.status == FunctionStatus.done
        # Generation was called twice (first rejected, second accepted) + critic
        assert mock_run.call_count == 3
        # Second generation call should contain the feedback about violations
        second_prompt = mock_run.call_args_list[1][0][0]
        assert "violation" in second_prompt.lower()
        assert "docstring" in second_prompt.lower()


class TestPromptUserReviewAuto:
    """Tests for prompt_user_review auto mode."""

    def test_auto_approves_without_input(self):
        """Test that auto=True returns approved without calling input."""
        approved, source = prompt_user_review("test code", auto=True)
        assert approved is True
        assert source == "test code"

    @patch("builtins.input", return_value="a")
    def test_auto_false_prompts_input(self, mock_input):
        """Test that auto=False prompts the user for input.

        Args:
            mock_input: Mocked builtins.input.
        """
        approved, source = prompt_user_review("test code", auto=False)
        assert approved is True
        mock_input.assert_called_once()


class TestPromptCritiqueReviewAuto:
    """Tests for prompt_critique_review auto mode."""

    def test_auto_accepts_without_input(self):
        """Test that auto=True returns True without calling input."""
        critique = TestCritique(
            exploit_vectors=["hardcode"],
            missing_edge_cases=["negative"],
            suggested_counter_tests=["test_neg"],
        )
        assert prompt_critique_review(critique, auto=True) is True

    @patch("builtins.input", return_value="d")
    def test_auto_false_prompts_input(self, mock_input):
        """Test that auto=False prompts the user for input.

        Args:
            mock_input: Mocked builtins.input.
        """
        critique = TestCritique(
            exploit_vectors=[],
            missing_edge_cases=[],
            suggested_counter_tests=[],
        )
        assert prompt_critique_review(critique, auto=False) is True
        mock_input.assert_called_once()


class TestPromptCritiqueReview:
    """Tests for prompt_critique_review."""

    @patch("builtins.input", return_value="d")
    def test_done_returns_true(self, _):
        """Test that choosing done returns True.

        Args:
            _: Mocked builtins.input returning "d".
        """
        critique = TestCritique(
            exploit_vectors=["hardcode"],
            missing_edge_cases=["negative"],
            suggested_counter_tests=["test_neg"],
        )
        assert prompt_critique_review(critique) is True

    @patch("builtins.input", return_value="i")
    def test_improve_returns_false(self, _):
        """Test that choosing improve returns False.

        Args:
            _: Mocked builtins.input returning "i".
        """
        critique = TestCritique(
            exploit_vectors=["hardcode"],
            missing_edge_cases=["negative"],
            suggested_counter_tests=["test_neg"],
        )
        assert prompt_critique_review(critique) is False

    @patch("builtins.input", side_effect=["x", "d"])
    def test_invalid_input_reprompts(self, _):
        """Test that invalid input reprompts until valid.

        Args:
            _: Mocked builtins.input returning "x" then "d".
        """
        critique = TestCritique(
            exploit_vectors=[],
            missing_edge_cases=[],
            suggested_counter_tests=[],
        )
        assert prompt_critique_review(critique) is True


class TestCritiqueRejectionRegenerates:
    """Test that critique rejection loops back to test generation."""

    @patch("orchestrator.loop.prompt_critique_review", side_effect=[False, True])
    @patch("orchestrator.loop.run_exploit_check", return_value=(False, ""))
    @patch("orchestrator.loop.run_cli_agent")
    @patch("orchestrator.loop.prompt_user_review")
    def test_critique_rejection_regenerates(
        self, mock_review, mock_run, mock_exploit, mock_critique
    ):
        """Test that rejecting critique triggers full regeneration cycle.

        Args:
            mock_review: Mocked prompt_user_review.
            mock_run: Mocked run_cli_agent.
            mock_exploit: Mocked run_exploit_check.
            mock_critique: Mocked prompt_critique_review (reject then accept).
        """
        mock_review.return_value = (True, _E2E_TEST_CODE)
        mock_run.side_effect = [
            # First cycle: generation
            CLIResult(
                stdout=f"```python\n{_E2E_TEST_CODE}\n```",
                stderr="", exit_code=0,
            ),
            # First cycle: critique (user rejects)
            CLIResult(stdout=_E2E_CRITIQUE_JSON, stderr="", exit_code=0),
            # Second cycle: generation
            CLIResult(
                stdout=f"```python\n{_E2E_TEST_CODE}\n```",
                stderr="", exit_code=0,
            ),
            # Second cycle: critique (user accepts)
            CLIResult(stdout=_E2E_CRITIQUE_JSON, stderr="", exit_code=0),
        ]
        progress = process_function(
            "add", _make_spec(), _make_constraints(), _make_config()
        )
        assert progress.status == FunctionStatus.done
        # 2 generation + 2 critique = 4 CLI calls
        assert mock_run.call_count == 4
        assert mock_critique.call_count == 2


# --- run_session ---


class TestRunSession:
    """Tests for run_session."""

    @patch("orchestrator.loop.process_function")
    @patch("orchestrator.loop.save_session")
    @patch("orchestrator.loop.load_session", return_value=None)
    def test_run_session_processes_all_functions(
        self, mock_load, mock_save, mock_process, tmp_path
    ):
        """Test that run_session processes each pending function.

        Args:
            mock_load: Mocked load_session returning None (new session).
            mock_save: Mocked save_session.
            mock_process: Mocked process_function.
            tmp_path: Pytest tmp_path fixture.
        """
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(
            "name: math\ndescription: Math utils\nfunctions:\n"
            "  - name: add\n    description: Add numbers\n"
            "  - name: sub\n    description: Sub numbers\n"
        )
        profiles_path = Path(__file__).parent.parent / "constraints" / "profiles.yaml"
        session_path = tmp_path / ".session.json"

        mock_process.return_value = FunctionProgress(
            name="add", status=FunctionStatus.done, test_source="test code",
        )
        state = run_session(spec_path, profiles_path, session_path)
        assert mock_process.call_count == 2

    @patch("orchestrator.loop.process_function")
    @patch("orchestrator.loop.save_session")
    @patch("orchestrator.loop.load_session")
    def test_run_session_skips_done_functions(
        self, mock_load, mock_save, mock_process, tmp_path
    ):
        """Test that run_session skips functions already marked done.

        Args:
            mock_load: Mocked load_session returning state with one done function.
            mock_save: Mocked save_session.
            mock_process: Mocked process_function.
            tmp_path: Pytest tmp_path fixture.
        """
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(
            "name: math\ndescription: Math utils\nfunctions:\n"
            "  - name: add\n    description: Add numbers\n"
            "  - name: sub\n    description: Sub numbers\n"
        )
        profiles_path = Path(__file__).parent.parent / "constraints" / "profiles.yaml"
        session_path = tmp_path / ".session.json"

        mock_load.return_value = SessionState(
            function_progress=[
                FunctionProgress(
                    name="add", status=FunctionStatus.done, test_source="code",
                ),
                FunctionProgress(name="sub", status=FunctionStatus.pending),
            ]
        )
        mock_process.return_value = FunctionProgress(
            name="sub", status=FunctionStatus.done, test_source="test code",
        )
        state = run_session(spec_path, profiles_path, session_path)
        # Only "sub" should be processed since "add" is already done
        assert mock_process.call_count == 1
        assert mock_process.call_args[0][0] == "sub"

    @patch("orchestrator.loop.run_implementation", return_value=True)
    @patch("orchestrator.loop.process_function")
    @patch("orchestrator.loop.save_session")
    @patch("orchestrator.loop.load_session", return_value=None)
    def test_run_session_auto_implement(
        self, mock_load, mock_save, mock_process, mock_impl, tmp_path
    ):
        """Test that auto_implement=True triggers run_implementation.

        Args:
            mock_load: Mocked load_session.
            mock_save: Mocked save_session.
            mock_process: Mocked process_function.
            mock_impl: Mocked run_implementation.
            tmp_path: Pytest tmp_path fixture.
        """
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(
            "name: add\ndescription: Add numbers\n"
        )
        profiles_path = Path(__file__).parent.parent / "constraints" / "profiles.yaml"
        session_path = tmp_path / ".session.json"

        mock_process.return_value = FunctionProgress(
            name="add", status=FunctionStatus.done, test_source="code",
        )
        run_session(
            spec_path, profiles_path, session_path, auto_implement=True,
        )
        mock_impl.assert_called_once()
