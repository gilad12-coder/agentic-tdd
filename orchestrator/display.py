"""Rich terminal display helpers for orchestrator output."""

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from orchestrator.models import SessionState, TestCritique

_console = Console()


def display_test_source(source: str, console: Console | None = None) -> None:
    """Print test source with Python syntax highlighting in a panel.

    Args:
        source: Generated Python test source code.
        console: Optional console override for tests.
    """
    c = console or _console
    syntax = Syntax(source, "python", line_numbers=False)
    c.print(Panel(syntax, title="Generated Tests", border_style="cyan"))


def display_critique_report(
    critique: TestCritique, console: Console | None = None
) -> None:
    """Print a critique report with color-coded sections.

    Args:
        critique: Structured critique produced by the critic model.
        console: Optional console override for tests.
    """
    c = console or _console
    sections = [
        ("Exploit vectors", "red", critique.exploit_vectors),
        ("Missing edge cases", "yellow", critique.missing_edge_cases),
        ("Suggested counter tests", "green", critique.suggested_counter_tests),
    ]
    c.print("[bold]Critique Report[/bold]")
    for title, color, items in sections:
        c.print(f"\n[bold]{title}[/bold]")
        if not items:
            c.print(f"[{color}]- (none)[/{color}]")
            continue
        for item in items:
            c.print(f"[{color}]- {item}[/{color}]")

    if critique.exploit_passed:
        c.print(
            "\n[bold red]Warning:[/bold red] exploit passed; generated tests are weak."
        )

    if critique.exploit_code:
        c.print(
            Panel(
                critique.exploit_code,
                title="Exploit Implementation",
                border_style="magenta",
            )
        )


def display_status_table(state: SessionState, console: Console | None = None) -> None:
    """Print a table summarizing per-function session progress.

    Args:
        state: Session state to display.
        console: Optional console override for tests.
    """
    c = console or _console
    table = Table(title="Session Status")
    table.add_column("Function")
    table.add_column("Status")
    table.add_column("Tests")
    table.add_column("Critique")

    for progress in state.function_progress:
        tests_value = "yes" if progress.test_source else "no"
        critique_value = "yes" if progress.critique else "no"
        table.add_row(progress.name, progress.status.value, tests_value, critique_value)
    c.print(table)


def display_error(message: str, console: Console | None = None) -> None:
    """Print an error message in red.

    Args:
        message: Error message to display.
        console: Optional console override for tests.
    """
    c = console or _console
    c.print(f"[red]Error: {message}[/red]")


def display_spinner_context(message: str):
    """Return a spinner context manager for status output.

    Args:
        message: Status message shown while work is in progress.

    Returns:
        Rich status context manager.
    """
    return _console.status(message)
