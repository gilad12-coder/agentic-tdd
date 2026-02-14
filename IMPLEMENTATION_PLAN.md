# Implementation Plan — Agentic TDD Phase 4 (Terminal Polish)

## Your Task

Update existing modules in `orchestrator/` and create `orchestrator/display.py` so that every test in `tests/` passes.

**What's new in Phase 4:**
- New `orchestrator/display.py` module with rich formatting functions
- `__main__.py` restructured with subparsers (`run` and `status`)
- `cli_runner.py` error handling for timeouts and missing binaries
- `critic.py` JSON extraction fallback for malformed LLM responses
- `loop.py` uses display functions, adds `[e]dit` option, error handling

**Rules:**
- Tests are READ-ONLY. Do not modify anything under `tests/`.
- Run `pytest tests/ -m "not llm" -v` after each change.
- Keep going until ALL tests pass.
- All your code must meet the constraints in `constraints/orchestrator.yaml`.
- Do NOT modify `models.py` or `config.py` — they are unchanged.

---

## Build Order

Steps 1–15 are already implemented and passing. **Start at Step 16.**

---

### Step 16: `orchestrator/display.py` (NEW FILE)

**Test file:** `tests/test_display.py`

**Create** this new module with all rich formatting functions. Each function accepts an optional `console: Console | None = None` parameter for testability (defaults to a module-level console).

```python
from rich.console import Console

_console = Console()

def display_test_source(source: str, console: Console | None = None) -> None:
    """Print test source with Python syntax highlighting in a panel."""

def display_critique_report(critique: TestCritique, console: Console | None = None) -> None:
    """Print critique report with colored sections."""

def display_status_table(state: SessionState, console: Console | None = None) -> None:
    """Print a rich table of function progress."""

def display_error(message: str, console: Console | None = None) -> None:
    """Print an error message in red."""

def display_spinner_context(message: str):
    """Return a context manager (console.status) for a spinner."""

def display_section_header(title: str, console: Console | None = None) -> None:
    """Print a section header rule."""
```

Implementation details:
- `display_test_source`: Use `rich.syntax.Syntax(source, "python")` inside a `rich.panel.Panel`.
- `display_critique_report`: Print each section with color markup:
  - Exploit vectors: `[red]`
  - Missing edge cases: `[yellow]`
  - Suggested counter tests: `[green]`
  - Empty sections: show "(none)"
- `display_status_table`: Use `rich.table.Table` with columns Function, Status, Tests, Critique.
- `display_error`: Use `console.print(f"[red]Error: {message}[/red]")` or similar.
- `display_spinner_context`: Return `_console.status(message)`.
- Each function: `c = console or _console` at the top.

**Failing tests to fix:**
- `test_display_test_source_contains_code` — source text must appear in output
- `test_display_critique_report_shows_all_sections` — all critique items in output
- `test_display_critique_report_empty_sections` — "none" for empty lists
- `test_display_status_table_shows_functions` — function names in output
- `test_display_status_table_mixed_statuses` — "done" and "pending" in output
- `test_display_error_contains_message` — error message in output
- `test_display_spinner_context_is_context_manager` — has `__enter__` and `__exit__`

**Verify:** `pytest tests/test_display.py -v`

---

### Step 17: `orchestrator/__main__.py`

**Test file:** `tests/test_main.py`

**Change:** Restructure to use argparse subparsers.

```python
import argparse
from pathlib import Path

from orchestrator.display import display_error
from orchestrator.loop import run_session
from orchestrator.session import load_session
from orchestrator.display import display_status_table


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atdd")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run")
    run_parser.add_argument("spec_path")
    run_parser.add_argument("--profiles", default="constraints/profiles.yaml")
    run_parser.add_argument("--session", default=".session.json")

    status_parser = sub.add_parser("status")
    status_parser.add_argument("--session", default=".session.json")

    return parser


def show_status(session_path: Path) -> None:
    state = load_session(session_path)
    if state is None:
        display_error(f"No session found at {session_path}")
        raise SystemExit(1)
    display_status_table(state)


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "run":
        spec_path = Path(args.spec_path)
        if not spec_path.exists():
            display_error(f"Spec file not found: {spec_path}")
            raise SystemExit(1)
        run_session(
            spec_path=spec_path,
            profiles_path=Path(args.profiles),
            session_path=Path(args.session),
        )
    elif args.command == "status":
        show_status(Path(args.session))
```

**Failing tests to fix:**
- `test_build_parser_run_subcommand` — `args.command == "run"`
- `test_build_parser_status_subcommand` — `args.command == "status"`
- `test_build_parser_run_default_profiles` — default profiles path
- `test_build_parser_run_default_session` — default session path
- `test_build_parser_status_default_session` — default session path
- `test_main_run_calls_run_session` — dispatch to run_session
- `test_main_status_calls_show_status` — dispatch to show_status
- `test_main_no_command_exits` — SystemExit on no subcommand
- `test_main_run_missing_spec_exits` — SystemExit on missing spec
- `test_main_status_missing_session_exits` — SystemExit on missing session

**Verify:** `pytest tests/test_main.py -v`

---

### Step 18: `orchestrator/cli_runner.py`

**Test file:** `tests/test_cli_runner.py`

**Change:** Add error handling to `run_cli_agent` for timeouts and missing binaries.

```python
def run_cli_agent(prompt, agent, model, budget, timeout=300) -> CLIResult:
    cmd = build_command(prompt, agent, model, budget)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return CLIResult(
            stdout="", stderr=f"Agent timed out after {timeout}s",
            exit_code=-1,
        )
    except FileNotFoundError:
        return CLIResult(
            stdout="",
            stderr=f"Agent binary not found: {cmd[0]}",
            exit_code=-1,
        )
    return parse_cli_output(result.stdout, result.stderr, result.returncode)
```

**Failing tests to fix:**
- `test_run_cli_agent_timeout_returns_error_result` — exit_code=-1, "timeout" in stderr
- `test_run_cli_agent_missing_binary_returns_error_result` — exit_code=-1, "not found" in stderr

**Verify:** `pytest tests/test_cli_runner.py -m "not llm" -v`

---

### Step 19: `orchestrator/critic.py`

**Test file:** `tests/test_critic.py`

**Change:** Add JSON extraction fallback to `parse_critique`.

```python
import re

def parse_critique(raw_json: str) -> TestCritique:
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, ValueError):
        data = _extract_json_from_text(raw_json)
    return TestCritique(**data)

def _extract_json_from_text(text: str) -> dict:
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON found in critique response")
```

**Failing test to fix:**
- `test_parse_critique_embedded_json_in_text` — extract JSON from surrounding text

**Important:** The existing `test_parse_critique_invalid_json` test must still pass — it expects `(ValueError, json.JSONDecodeError)` for text with no JSON.

**Verify:** `pytest tests/test_critic.py -v`

---

### Step 20: `orchestrator/loop.py`

**Test file:** `tests/test_loop.py`

**Changes:**

1. **Import display functions** at the top:
```python
from orchestrator.display import (
    display_error,
    display_spinner_context,
    display_test_source,
    display_critique_report,
)
```

2. **Update `prompt_user_review`** — add `[e]dit` option:
```python
def prompt_user_review(test_source: str) -> tuple[bool, str]:
    display_test_source(test_source)
    while True:
        decision = input(
            "Review: [a]pprove / [e]dit / [r]egenerate: "
        ).strip().lower()
        if decision in {"a", "approve"}:
            return True, test_source
        if decision in {"r", "regenerate"}:
            return False, ""
        if decision in {"e", "edit"}:
            edited = _open_in_editor(test_source)
            if edited is not None:
                test_source = edited
                display_test_source(test_source)
            continue
        print("Enter 'a', 'e', or 'r'.")
```

3. **Add `_open_in_editor` helper:**
```python
def _open_in_editor(source: str) -> str | None:
    import os
    import tempfile
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False
    ) as f:
        f.write(source)
        tmp_path = f.name
    try:
        subprocess.run([editor, tmp_path], check=True)
        return Path(tmp_path).read_text()
    except (subprocess.CalledProcessError, FileNotFoundError):
        display_error(f"Could not open editor: {editor}")
        return None
    finally:
        Path(tmp_path).unlink(missing_ok=True)
```

4. **Update `generate_tests`** — add error handling:
```python
def generate_tests(spec, constraints, config):
    prompt = build_generation_prompt(spec, constraints)
    with display_spinner_context("Generating tests..."):
        result = run_cli_agent(...)
    if result.exit_code != 0:
        display_error(f"Generation failed: {result.stderr}")
        return ""
    return extract_python_from_response(result.stdout)
```

5. **Update `run_critique`** — add spinner:
```python
def run_critique(test_source, spec, config, constraints=None):
    prompt = build_critic_prompt(test_source, spec, constraints)
    with display_spinner_context("Running critique..."):
        result = run_cli_agent(...)
    return parse_critique(result.stdout)
```

6. **Update `print_critique_report`** — delegate to display:
```python
def print_critique_report(critique: TestCritique) -> None:
    display_critique_report(critique)
```

7. **Remove `_print_section`** — no longer used.

**Failing tests to fix:**
- `test_prompt_user_review_edit_then_approve` — edit then approve returns edited code
- `test_prompt_user_review_edit_failure_continues` — editor failure keeps original code
- `test_generate_tests_agent_failure_returns_empty` — exit_code=-1 returns ""

**Important:** Existing tests must still pass:
- `test_generate_tests_calls_cli_agent_with_prompt`
- `test_generate_tests_extracts_python`
- `test_run_critique_*`
- `test_process_function_*`
- `test_print_critique_report_outputs_all_sections` (capsys — strings must still appear in stdout)
- `test_run_implementation_*`

**Verify:** `pytest tests/test_loop.py -v`

---

## Self-Constraints Check

```bash
pytest tests/test_self_constraints.py -v
```

All modified files and new `display.py` must still meet primary (cc≤15, lines≤80) and secondary (Google docstrings) constraints.

---

## Final Verification

```bash
pytest tests/ -m "not llm" -v
```

ALL tests must pass (~146 tests).

---

## File Map

```
orchestrator/
├── models.py            ← no changes
├── config.py            ← no changes
├── display.py           ← Step 16 (NEW: all rich formatting)
├── __main__.py          ← Step 17 (subparsers, status, error checks)
├── cli_runner.py        ← Step 18 (timeout/missing-binary handling)
├── critic.py            ← Step 19 (JSON extraction fallback)
├── loop.py              ← Step 20 (display calls, edit flow, error handling)
├── session.py           ← no changes
├── spec_intake.py       ← no changes
├── constraint_checks.py ← no changes
└── constraint_loader.py ← no changes
```
