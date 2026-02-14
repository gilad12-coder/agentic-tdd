"""Tests for the rich display module."""

import io

from rich.console import Console

from orchestrator.display import (
    display_critique_report,
    display_error,
    display_spinner_context,
    display_status_table,
    display_test_source,
)
from orchestrator.models import (
    FunctionProgress,
    FunctionStatus,
    SessionState,
    TestCritique,
)


def _capture_console() -> tuple[Console, io.StringIO]:
    """Create a console that captures output to a string buffer."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True)
    return console, buf


# --- display_test_source ---


class TestDisplayTestSource:
    def test_display_test_source_contains_code(self):
        console, buf = _capture_console()
        source = "def test_add():\n    assert add(1, 2) == 3"
        display_test_source(source, console=console)
        output = buf.getvalue()
        assert "test_add" in output
        assert "assert" in output


# --- display_critique_report ---


class TestDisplayCritiqueReport:
    def test_display_critique_report_shows_all_sections(self):
        console, buf = _capture_console()
        critique = TestCritique(
            exploit_vectors=["hardcode return"],
            missing_edge_cases=["empty input"],
            suggested_counter_tests=["def test_empty(): ..."],
        )
        display_critique_report(critique, console=console)
        output = buf.getvalue()
        assert "hardcode return" in output
        assert "empty input" in output
        assert "test_empty" in output

    def test_display_critique_report_empty_sections(self):
        console, buf = _capture_console()
        critique = TestCritique(
            exploit_vectors=[],
            missing_edge_cases=[],
            suggested_counter_tests=[],
        )
        display_critique_report(critique, console=console)
        output = buf.getvalue()
        assert "none" in output.lower()


# --- display_status_table ---


class TestDisplayStatusTable:
    def test_display_status_table_shows_functions(self):
        console, buf = _capture_console()
        state = SessionState(
            function_progress=[
                FunctionProgress(name="add", status=FunctionStatus.done),
                FunctionProgress(name="subtract", status=FunctionStatus.pending),
            ]
        )
        display_status_table(state, console=console)
        output = buf.getvalue()
        assert "add" in output
        assert "subtract" in output

    def test_display_status_table_mixed_statuses(self):
        console, buf = _capture_console()
        state = SessionState(
            function_progress=[
                FunctionProgress(
                    name="add",
                    status=FunctionStatus.done,
                    test_source="def test_add(): pass",
                    critique=TestCritique(
                        exploit_vectors=[],
                        missing_edge_cases=[],
                        suggested_counter_tests=[],
                    ),
                ),
                FunctionProgress(name="sub", status=FunctionStatus.pending),
            ]
        )
        display_status_table(state, console=console)
        output = buf.getvalue()
        assert "done" in output
        assert "pending" in output


# --- display_error ---


class TestDisplayError:
    def test_display_error_contains_message(self):
        console, buf = _capture_console()
        display_error("Something went wrong", console=console)
        output = buf.getvalue()
        assert "Something went wrong" in output


# --- display_spinner_context ---


class TestDisplayCritiqueReportExploit:
    def test_display_critique_report_shows_exploit_warning(self):
        console, buf = _capture_console()
        critique = TestCritique(
            exploit_vectors=["hardcode"],
            missing_edge_cases=[],
            suggested_counter_tests=[],
            exploit_passed=True,
            exploit_code="def add(a, b): return 3",
        )
        display_critique_report(critique, console=console)
        output = buf.getvalue()
        # Must show a specific warning about tests being weak/exploitable
        assert "weak" in output.lower() or "exploit passed" in output.lower()

    def test_display_critique_report_shows_exploit_code(self):
        console, buf = _capture_console()
        critique = TestCritique(
            exploit_vectors=[],
            missing_edge_cases=[],
            suggested_counter_tests=[],
            exploit_passed=False,
            exploit_code="def add(a, b): return {(1,2): 3}.get((a,b), 0)",
        )
        display_critique_report(critique, console=console)
        output = buf.getvalue()
        assert "def add" in output


class TestDisplaySpinnerContext:
    def test_display_spinner_context_is_context_manager(self):
        ctx = display_spinner_context("Loading...")
        assert hasattr(ctx, "__enter__")
        assert hasattr(ctx, "__exit__")
