"""Main orchestration loop for test generation, review, and critique."""

import subprocess
from pathlib import Path

from orchestrator.cli_runner import build_implementation_command, run_cli_agent
from orchestrator.config import Config
from orchestrator.constraint_loader import load_profiles, resolve_constraints
from orchestrator.critic import parse_critique, run_exploit_check
from orchestrator.prompts import (
    build_critic_prompt,
    build_generation_prompt,
    build_implementation_prompt,
)
from orchestrator.display import (
    display_critique_report,
    display_error,
    display_spinner_context,
    display_test_source,
)
from orchestrator.models import (
    FunctionProgress,
    FunctionStatus,
    ParsedSpec,
    SessionState,
    TaskConstraints,
    TestCritique,
)
from orchestrator.session import create_session, load_session, save_session
from orchestrator.spec_intake import parse_spec
from orchestrator.test_generator import extract_python_from_response


def run_session(spec_path: Path, profiles_path: Path, session_path: Path) -> SessionState:
    """Run or resume an orchestrator session for all unfinished functions.

    Args:
        spec_path: Path to the task specification YAML file.
        profiles_path: Path to the constraints profiles YAML file.
        session_path: Path to persisted session JSON state.

    Returns:
        Final session state after processing pending functions.
    """
    spec = parse_spec(spec_path)
    profiles = load_profiles(profiles_path)
    config = Config()

    state = load_session(session_path)
    if state is None:
        state = create_session(spec)
        save_session(state, session_path)

    for index, progress in enumerate(state.function_progress):
        if progress.status == FunctionStatus.done:
            continue
        constraints = resolve_constraints(spec, profiles, progress.name)
        updated = process_function(progress.name, spec, constraints, config)
        state.function_progress[index] = updated
        save_session(state, session_path)

    return state


def process_function(
    func_name: str, spec: ParsedSpec, constraints: TaskConstraints, config: Config
) -> FunctionProgress:
    """Generate tests for one function, request approval, then run critique.

    Args:
        func_name: Name of the function being processed.
        spec: Parsed task specification.
        constraints: Resolved constraints for this function.
        config: Runtime configuration for model selection and limits.

    Returns:
        Completed function progress object including tests and critique.
    """
    function_spec = _spec_for_function(spec, func_name)
    approved_source = ""
    max_attempts = max(config.max_iterations, 1)

    for _ in range(max_attempts):
        test_source = generate_tests(function_spec, constraints, config)
        approved, selected_source = prompt_user_review(test_source)
        if approved:
            approved_source = selected_source
            break
    else:
        raise RuntimeError(
            f"Exceeded max_iterations={config.max_iterations} for {func_name}"
        )

    critique = run_critique(
        approved_source,
        function_spec,
        config,
        constraints=constraints,
    )
    exploit_passed, exploit_code = run_exploit_check(
        approved_source,
        function_spec,
        config,
    )
    critique.exploit_passed = exploit_passed
    critique.exploit_code = exploit_code
    print_critique_report(critique)
    return FunctionProgress(
        name=func_name,
        status=FunctionStatus.done,
        test_source=approved_source,
        critique=critique,
    )


def generate_tests(spec: ParsedSpec, constraints: TaskConstraints, config: Config) -> str:
    """Generate pytest test source for a parsed spec using the generation agent.

    Args:
        spec: Parsed function or task specification.
        constraints: Constraints to include in the generation prompt.
        config: Runtime configuration for generation model and budget.

    Returns:
        Extracted Python test source code.
    """
    prompt = build_generation_prompt(spec, constraints)
    with display_spinner_context("Generating tests..."):
        result = run_cli_agent(
            prompt,
            config.generation_agent,
            config.generation_model,
            config.max_budget_usd,
        )
    if result.exit_code != 0:
        display_error(f"Generation failed: {result.stderr}")
        return ""
    return extract_python_from_response(result.stdout)


def prompt_user_review(test_source: str) -> tuple[bool, str]:
    """Prompt the user to approve or regenerate generated test source.

    Args:
        test_source: Generated Python test source code.

    Returns:
        Tuple of (approved, selected_source). Rejected output returns empty source.
    """
    display_test_source(test_source)

    while True:
        decision = input("Review: [a]pprove / [e]dit / [r]egenerate: ").strip().lower()
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


def run_critique(
    test_source: str,
    spec: ParsedSpec,
    config: Config,
    constraints: TaskConstraints | None = None,
) -> TestCritique:
    """Run the critic model on approved tests and parse critique output.

    Args:
        test_source: Approved Python test source code.
        spec: Parsed function or task specification for context.
        config: Runtime configuration for critic model and budget.
        constraints: Optional constraints used for critic evaluation.

    Returns:
        Structured critique of the generated tests.
    """
    prompt = build_critic_prompt(test_source, spec, constraints)
    with display_spinner_context("Running critique..."):
        result = run_cli_agent(
            prompt,
            config.critic_agent,
            config.critic_model,
            config.max_budget_usd,
        )
    return parse_critique(result.stdout)


def print_critique_report(critique: TestCritique) -> None:
    """Print a human-readable critique report to stdout.

    Args:
        critique: Structured critique to display.
    """
    display_critique_report(critique)


def _open_in_editor(source: str) -> str | None:
    """Open source code in the user's editor and return edited content.

    Args:
        source: Current generated test source to edit.

    Returns:
        Edited source text when editing succeeds, otherwise None.
    """
    import os
    import tempfile

    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(
        suffix=".py",
        mode="w",
        encoding="utf-8",
        delete=False,
    ) as temp_file:
        temp_file.write(source)
        temp_path = Path(temp_file.name)
    try:
        subprocess.run([editor, str(temp_path)], check=True)
        return temp_path.read_text(encoding="utf-8")
    except (subprocess.CalledProcessError, FileNotFoundError):
        display_error(f"Could not open editor: {editor}")
        return None
    finally:
        temp_path.unlink(missing_ok=True)


def run_implementation(
    state: SessionState,
    config: Config,
    test_dir: Path = Path("tests"),
) -> bool:
    """Run implementation generation and verify by executing pytest.

    Args:
        state: Session state containing approved test source per function.
        config: Runtime configuration for implementation model selection.
        test_dir: Directory where generated tests are written.

    Returns:
        True when pytest exits with code 0, otherwise False.
    """
    test_dir.mkdir(parents=True, exist_ok=True)
    generated_paths = _write_generated_tests(state, test_dir)
    prompt = build_implementation_prompt(generated_paths)
    command = build_implementation_command(
        prompt,
        config.implementation_agent,
        config.implementation_model,
    )
    subprocess.run(command, capture_output=True, text=True)
    pytest_result = subprocess.run(
        ["pytest", str(test_dir), "-v"],
        capture_output=True,
        text=True,
    )
    return pytest_result.returncode == 0


def _spec_for_function(spec: ParsedSpec, func_name: str) -> ParsedSpec:
    """Create a function-scoped spec for prompt generation and critique.

    Args:
        spec: Parsed task specification.
        func_name: Function name to resolve in the task spec.

    Returns:
        Function-level ParsedSpec, or the original-level details when unmatched.
    """
    for function_spec in spec.functions:
        if function_spec.name == func_name:
            return ParsedSpec(
                name=function_spec.name,
                description=function_spec.description or spec.description,
                examples=function_spec.examples or spec.examples,
                signature=function_spec.signature or spec.signature,
                constraint_profile=function_spec.constraint_profile
                or spec.constraint_profile,
                target_files=list(spec.target_files),
                functions=list(spec.functions),
            )
    return ParsedSpec(
        name=func_name,
        description=spec.description,
        examples=spec.examples,
        signature=spec.signature,
        constraint_profile=spec.constraint_profile,
        target_files=list(spec.target_files),
        functions=list(spec.functions),
    )


def _write_generated_tests(state: SessionState, test_dir: Path) -> list[Path]:
    """Write approved generated tests from session state to disk.

    Args:
        state: Session state containing per-function progress.
        test_dir: Directory to place generated test files.

    Returns:
        Paths of test files written in this run.
    """
    written_paths = []
    for progress in state.function_progress:
        if not progress.test_source:
            continue
        path = test_dir / f"test_{progress.name}.py"
        path.write_text(progress.test_source)
        written_paths.append(path)
    return written_paths

