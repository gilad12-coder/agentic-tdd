"""Tests for the rich display module."""

import io
import re

from rich.console import Console

from orchestrator.display import (
    display_critique_report,
    display_docker_status,
    display_error,
    display_function_header,
    display_implementation_attempt,
    display_implementation_result,
    display_session_complete,
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
    """Create a console that captures output to a string buffer.

    Returns:
        Tuple of (Console, StringIO buffer).
    """
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True)
    return console, buf


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text.

    Args:
        text: Text potentially containing ANSI escape sequences.

    Returns:
        Plain text with all escape codes removed.
    """
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


# --- display_test_source ---


class TestDisplayTestSource:
    """Tests for display_test_source."""

    def test_display_test_source_contains_code(self):
        """Test that display_test_source renders code content."""
        console, buf = _capture_console()
        source = "def test_add():\n    assert add(1, 2) == 3"
        display_test_source(source, console=console)
        output = buf.getvalue()
        assert "test_add" in output
        assert "assert" in output


# --- display_critique_report ---


class TestDisplayCritiqueReport:
    """Tests for display_critique_report."""

    def test_display_critique_report_shows_all_sections(self):
        """Test that display_critique_report shows exploit vectors, edge cases, and tests."""
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
        """Test that display_critique_report handles empty sections gracefully."""
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
    """Tests for display_status_table."""

    def test_display_status_table_shows_functions(self):
        """Test that display_status_table shows function names."""
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
        """Test that display_status_table shows both done and pending statuses."""
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
    """Tests for display_error."""

    def test_display_error_contains_message(self):
        """Test that display_error renders the error message."""
        console, buf = _capture_console()
        display_error("Something went wrong", console=console)
        output = buf.getvalue()
        assert "Something went wrong" in output


# --- display_spinner_context ---


class TestDisplayCritiqueReportExploit:
    """Tests for exploit display in critique reports."""

    def test_display_critique_report_shows_exploit_warning(self):
        """Test that display_critique_report shows a warning when exploit passes."""
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
        """Test that display_critique_report shows the exploit code."""
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


class TestDisplayFunctionHeader:
    """Tests for display_function_header."""

    def test_display_function_header_contains_name(self):
        """Test that display_function_header renders the function name."""
        console, buf = _capture_console()
        display_function_header("add", console=console)
        output = buf.getvalue()
        assert "add" in output

    def test_display_function_header_contains_processing_label(self):
        """Test that display_function_header shows 'Processing' label."""
        console, buf = _capture_console()
        display_function_header("merge_intervals", console=console)
        output = buf.getvalue()
        assert "Processing" in output


class TestDisplaySessionComplete:
    """Tests for display_session_complete."""

    def test_display_session_complete_shows_count(self):
        """Test that display_session_complete shows done/total count."""
        console, buf = _capture_console()
        state = SessionState(
            function_progress=[
                FunctionProgress(name="add", status=FunctionStatus.done),
                FunctionProgress(name="sub", status=FunctionStatus.pending),
            ]
        )
        display_session_complete(state, console=console)
        output = _strip_ansi(buf.getvalue())
        assert "1/2" in output

    def test_display_session_complete_all_done(self):
        """Test that display_session_complete shows all done."""
        console, buf = _capture_console()
        state = SessionState(
            function_progress=[
                FunctionProgress(name="add", status=FunctionStatus.done),
                FunctionProgress(name="sub", status=FunctionStatus.done),
            ]
        )
        display_session_complete(state, console=console)
        output = _strip_ansi(buf.getvalue())
        assert "2/2" in output


class TestDisplayImplementationAttempt:
    """Tests for display_implementation_attempt."""

    def test_display_implementation_attempt_shows_numbers(self):
        """Test that display_implementation_attempt shows attempt/max."""
        console, buf = _capture_console()
        display_implementation_attempt(3, 10, console=console)
        output = _strip_ansi(buf.getvalue())
        assert "3/10" in output

    def test_display_implementation_attempt_contains_attempt_label(self):
        """Test that display_implementation_attempt shows 'attempt' label."""
        console, buf = _capture_console()
        display_implementation_attempt(1, 5, console=console)
        output = buf.getvalue()
        assert "attempt" in output.lower()


class TestDisplayImplementationResult:
    """Tests for display_implementation_result."""

    def test_display_implementation_result_passed(self):
        """Test that passed=True shows success message."""
        console, buf = _capture_console()
        display_implementation_result(True, console=console)
        output = buf.getvalue()
        assert "passed" in output.lower()

    def test_display_implementation_result_failed(self):
        """Test that passed=False shows failure message."""
        console, buf = _capture_console()
        display_implementation_result(False, console=console)
        output = buf.getvalue()
        assert "failed" in output.lower()


class TestDisplayDockerStatus:
    """Tests for display_docker_status."""

    def test_display_docker_status_available(self):
        """Test that available=True shows Docker available message."""
        console, buf = _capture_console()
        display_docker_status(True, console=console)
        output = buf.getvalue()
        assert "available" in output.lower()

    def test_display_docker_status_unavailable(self):
        """Test that available=False shows Docker not available message."""
        console, buf = _capture_console()
        display_docker_status(False, console=console)
        output = buf.getvalue()
        assert "not available" in output.lower()


class TestDisplaySpinnerContext:
    """Tests for display_spinner_context."""

    def test_display_spinner_context_is_context_manager(self):
        """Test that display_spinner_context returns a context manager."""
        ctx = display_spinner_context("Loading...")
        assert hasattr(ctx, "__enter__")
        assert hasattr(ctx, "__exit__")
