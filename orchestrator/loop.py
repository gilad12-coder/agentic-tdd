"""Main orchestration loop for test generation, review, and critique."""

import subprocess
import tempfile
from pathlib import Path

from orchestrator.cli_runner import build_implementation_command, run_cli_agent
from orchestrator.config import Config
from orchestrator.constraint_checks import check_constraints
from orchestrator.constraint_loader import load_profiles, resolve_constraints
from orchestrator.critic import (
    parse_critique,
    run_exploit_check,
    verify_exploit_with_hidden_evals,
)
from orchestrator.prompts import (
    build_critic_prompt,
    build_generation_prompt,
    build_implementation_prompt,
)
from orchestrator.display import (
    display_critique_report,
    display_docker_status,
    display_error,
    display_function_header,
    display_implementation_attempt,
    display_implementation_result,
    display_session_complete,
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


def run_session(
    spec_path: Path,
    profiles_path: Path,
    session_path: Path,
    auto_tests: bool = False,
    auto_critique: bool = False,
    auto_implement: bool = False,
) -> SessionState:
    """Run or resume an orchestrator session for all unfinished functions.

    Args:
        spec_path: Path to the task specification YAML file.
        profiles_path: Path to the constraints profiles YAML file.
        session_path: Path to persisted session JSON state.
        auto_tests: When True, auto-approve generated tests.
        auto_critique: When True, auto-accept critique reviews.
        auto_implement: When True, run implementation after all functions done.

    Returns:
        Final session state after processing pending functions.
    """
    spec = parse_spec(spec_path)
    profiles = load_profiles(profiles_path)
    config = Config()
    workspace = spec_path.parent

    if not session_path.is_absolute():
        session_path = workspace / session_path

    state = load_session(session_path)
    if state is None:
        state = create_session(spec)
        save_session(state, session_path)

    for index, progress in enumerate(state.function_progress):
        if progress.status == FunctionStatus.done:
            continue
        constraints = resolve_constraints(spec, profiles, progress.name)
        display_function_header(progress.name)
        updated = process_function(
            progress.name, spec, constraints, config,
            auto_tests=auto_tests, auto_critique=auto_critique,
        )
        state.function_progress[index] = updated
        save_session(state, session_path)

    display_session_complete(state)

    if auto_implement:
        from orchestrator.sandbox import check_docker_available

        use_docker = check_docker_available()
        display_docker_status(use_docker)
        constraints_map = {
            p.name: resolve_constraints(spec, profiles, p.name)
            for p in state.function_progress
        }
        success = run_implementation(
            state, config,
            test_dir=workspace / "tests",
            spec=spec,
            constraints_map=constraints_map, use_docker=use_docker,
        )
        display_implementation_result(success)

    return state


def process_function(
    func_name: str,
    spec: ParsedSpec,
    constraints: TaskConstraints,
    config: Config,
    auto_tests: bool = False,
    auto_critique: bool = False,
) -> FunctionProgress:
    """Generate tests for one function, request approval, then run critique.

    Args:
        func_name: Name of the function being processed.
        spec: Parsed task specification.
        constraints: Resolved constraints for this function.
        config: Runtime configuration for model selection and limits.
        auto_tests: When True, auto-approve generated tests.
        auto_critique: When True, auto-accept critique reviews.

    Returns:
        Completed function progress object including tests and critique.
    """
    function_spec = _spec_for_function(spec, func_name)
    max_attempts = max(config.max_iterations, 1)

    max_critique_cycles = 2 if auto_critique else max_attempts
    critique_feedback = ""
    for _ in range(max_critique_cycles):
        approved_source = _generate_and_approve(
            function_spec, constraints, config, max_attempts, critique_feedback,
            auto=auto_tests,
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
        if exploit_passed and exploit_code and function_spec.hidden_evals:
            if verify_exploit_with_hidden_evals(
                exploit_code, function_spec.name, function_spec.hidden_evals
            ):
                exploit_passed = False
        critique.exploit_passed = exploit_passed
        critique.exploit_code = exploit_code
        if prompt_critique_review(critique, auto=auto_critique):
            return FunctionProgress(
                name=func_name,
                status=FunctionStatus.done,
                test_source=approved_source,
                critique=critique,
            )
        critique_feedback = _format_critique_feedback(critique)
    return FunctionProgress(
        name=func_name,
        status=FunctionStatus.done,
        test_source=approved_source,
        critique=critique,
    )


def _generate_and_approve(
    function_spec: ParsedSpec,
    constraints: TaskConstraints,
    config: Config,
    max_attempts: int,
    critique_feedback: str = "",
    auto: bool = False,
) -> str:
    """Run the generate → validate → user review loop until tests are approved.

    Args:
        function_spec: Parsed spec for the specific function.
        constraints: Resolved constraints for this function.
        config: Runtime configuration for generation.
        max_attempts: Maximum generation attempts before raising.
        critique_feedback: Critic findings from a previous cycle to address.
        auto: When True, skip interactive prompts and auto-accept.

    Returns:
        User-approved test source code.
    """
    constraint_feedback = ""
    for _ in range(max_attempts):
        test_source = generate_tests(
            function_spec, constraints, config, constraint_feedback,
            critique_feedback,
        )
        if not test_source:
            continue
        syntax_ok, errors = validate_test_syntax(test_source)
        if not syntax_ok:
            display_error(f"Generated tests have syntax errors:\n{errors}")
            display_error("Regenerating...")
            continue
        constraints_ok, violations = validate_test_constraints(test_source, constraints)
        if not constraints_ok:
            display_error(f"Generated tests violate constraints:\n{violations}")
            display_error(
                "Regenerating — feeding violations back to the agent..."
            )
            constraint_feedback = violations
            continue
        constraint_feedback = ""
        approved, selected_source = prompt_user_review(test_source, auto=auto)
        if approved:
            return selected_source
    raise RuntimeError(
        f"Exceeded max_iterations={config.max_iterations} for test generation"
    )


def generate_tests(
    spec: ParsedSpec,
    constraints: TaskConstraints,
    config: Config,
    constraint_feedback: str = "",
    critique_feedback: str = "",
) -> str:
    """Generate pytest test source for a parsed spec using the generation agent.

    Args:
        spec: Parsed function or task specification.
        constraints: Constraints to include in the generation prompt.
        config: Runtime configuration for generation model and budget.
        constraint_feedback: Violations from a previous attempt to fix on retry.
        critique_feedback: Critic findings from a previous cycle to address.

    Returns:
        Extracted Python test source code.
    """
    prompt = build_generation_prompt(
        spec, constraints, constraint_feedback, critique_feedback
    )
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


def prompt_user_review(test_source: str, auto: bool = False) -> tuple[bool, str]:
    """Prompt the user to approve or regenerate generated test source.

    Args:
        test_source: Generated Python test source code.
        auto: When True, auto-approve without prompting.

    Returns:
        Tuple of (approved, selected_source). Rejected output returns empty source.
    """
    display_test_source(test_source)
    if auto:
        return True, test_source

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


def prompt_critique_review(critique: TestCritique, auto: bool = False) -> bool:
    """Display critique results and prompt user to finish or improve tests.

    Args:
        critique: Structured critique of generated tests.
        auto: When True, auto-done without prompting.

    Returns:
        True if done (move on), False to improve tests using critique feedback.
    """
    display_critique_report(critique)
    if auto:
        return not getattr(critique, "exploit_passed", False)

    while True:
        decision = input("Critique: [i]mprove tests / [d]one: ").strip().lower()
        if decision in {"d", "done"}:
            return True
        if decision in {"i", "improve"}:
            return False
        print("Enter 'i' or 'd'.")


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


def validate_test_syntax(test_source: str) -> tuple[bool, str]:
    """Check that generated test source has valid Python syntax.

    Args:
        test_source: Generated Python test source code.

    Returns:
        Tuple of (passed, error_output). passed is True if syntax is valid.
    """
    import ast

    try:
        ast.parse(test_source)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    if not test_source.strip():
        return False, "Empty test source"
    return True, ""


def validate_test_constraints(
    test_source: str, constraints: TaskConstraints
) -> tuple[bool, str]:
    """Check that generated test source satisfies the task constraints.

    Args:
        test_source: Generated Python test source code.
        constraints: Resolved constraints for this function.

    Returns:
        Tuple of (passed, error_output). passed is True if all constraints met.
    """
    primary, secondary = check_constraints(test_source, constraints)
    violations = primary.violations + secondary.violations
    if violations:
        return False, "\n".join(violations)
    return True, ""


def run_implementation(
    state: SessionState,
    config: Config,
    test_dir: Path = Path("tests"),
    spec: ParsedSpec | None = None,
    constraints_map: dict[str, TaskConstraints] | None = None,
    use_docker: bool = False,
) -> bool:
    """Run implementation generation with retry loop and optional Docker.

    When *spec* and *constraints_map* are provided, a ``plan.md`` is
    generated and included in the agent prompt.  The implementation agent
    runs on the host while pytest verification can optionally run inside
    a Docker container for isolation.

    Args:
        state: Session state containing approved test source per function.
        config: Runtime configuration for implementation model selection.
        test_dir: Directory where generated tests are written.
        spec: Optional parsed spec for plan generation.
        constraints_map: Optional map of function name to constraints.
        use_docker: When True, run pytest inside a Docker container.

    Returns:
        True when all tests pass, otherwise False after max retries.
    """
    test_dir.mkdir(parents=True, exist_ok=True)
    generated_paths = _write_generated_tests(state, test_dir)

    plan_path = None
    if spec is not None and constraints_map is not None:
        from orchestrator.plan_generator import (
            build_implementation_plan,
            write_plan_to_workspace,
        )
        plan_content = build_implementation_plan(state, spec, constraints_map)
        plan_path = write_plan_to_workspace(plan_content, test_dir.parent)

    hidden_specs = _collect_hidden_eval_specs(state, spec)
    max_attempts = max(config.max_iterations, 1)
    error_feedback = ""
    for attempt in range(1, max_attempts + 1):
        display_implementation_attempt(attempt, max_attempts)
        prompt = build_implementation_prompt(
            generated_paths, plan_path, error_feedback,
        )
        command = build_implementation_command(
            prompt, config.implementation_agent, config.implementation_model,
        )
        try:
            impl_result = subprocess.run(
                command,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            error_feedback = _format_agent_failure_feedback(
                returncode=-1,
                stdout="",
                stderr=f"Agent binary not found: {exc}",
            )
            continue

        if impl_result.returncode != 0:
            error_feedback = _format_agent_failure_feedback(
                returncode=impl_result.returncode,
                stdout=impl_result.stdout,
                stderr=impl_result.stderr,
            )
            continue

        passed, error_feedback = _verify_tests(test_dir, use_docker, hidden_specs)
        if passed:
            return True

    return False


def _verify_tests(
    test_dir: Path,
    use_docker: bool,
    hidden_specs: dict[str, ParsedSpec] | None = None,
) -> tuple[bool, str]:
    """Run public pytest checks, then optional hidden eval checks.

    Args:
        test_dir: Directory containing test files.
        use_docker: When True, run pytest inside a Docker container.
        hidden_specs: Optional function-scoped specs with hidden evals.

    Returns:
        Tuple of (passed, error_output).
    """
    public_passed, public_output = _run_pytest_targets(
        workspace=test_dir.parent, targets=[test_dir], use_docker=use_docker
    )
    if not public_passed:
        return False, public_output
    if not hidden_specs:
        return True, ""
    hidden_passed, hidden_output = _run_hidden_eval_checks(
        test_dir=test_dir, use_docker=use_docker, hidden_specs=hidden_specs
    )
    if hidden_passed:
        return True, ""
    if hidden_output.startswith("HIDDEN EVAL CONFIG ERROR:"):
        return False, hidden_output
    return False, _redacted_hidden_failure_feedback(hidden_output, hidden_specs)


def _collect_hidden_eval_specs(
    state: SessionState, spec: ParsedSpec | None
) -> dict[str, ParsedSpec]:
    """Collect per-function specs that include hidden evals.

    Args:
        state: Session state containing function progress entries.
        spec: Parsed task specification, or None if unavailable.

    Returns:
        Mapping of function name to function-scoped ParsedSpec with hidden evals.
    """
    if spec is None:
        return {}
    hidden_specs = {}
    for progress in state.function_progress:
        if not progress.test_source:
            continue
        function_spec = _spec_for_function(spec, progress.name)
        if function_spec.hidden_evals:
            hidden_specs[progress.name] = function_spec
    return hidden_specs


def _run_pytest_targets(
    workspace: Path, targets: list[Path], use_docker: bool
) -> tuple[bool, str]:
    """Run pytest for the provided targets via host or Docker.

    Args:
        workspace: Root workspace directory for Docker-relative paths.
        targets: List of test file or directory paths to run.
        use_docker: When True, run pytest inside a Docker container.

    Returns:
        Tuple of (passed, combined_output).
    """
    if use_docker:
        from orchestrator.sandbox import run_pytest_in_docker

        docker_targets = []
        for target in targets:
            if target.is_absolute():
                try:
                    docker_targets.append(str(target.relative_to(workspace)))
                except ValueError:
                    docker_targets.append(str(target))
            else:
                docker_targets.append(str(target))
        result = run_pytest_in_docker(workspace, test_targets=docker_targets)
        return result.passed, result.stdout + result.stderr

    pytest_result = subprocess.run(
        ["pytest", *(str(target) for target in targets), "-v"],
        capture_output=True,
        text=True,
    )
    return pytest_result.returncode == 0, pytest_result.stdout + pytest_result.stderr


def _run_hidden_eval_checks(
    test_dir: Path, use_docker: bool, hidden_specs: dict[str, ParsedSpec]
) -> tuple[bool, str]:
    """Run hidden eval assertions from ephemeral test files.

    Args:
        test_dir: Directory containing public test files.
        use_docker: When True, run pytest inside a Docker container.
        hidden_specs: Mapping of function name to spec with hidden evals.

    Returns:
        Tuple of (passed, combined_output).
    """
    workspace = test_dir.parent
    with tempfile.TemporaryDirectory(
        dir=workspace, prefix=".atdd_hidden_eval_"
    ) as temp_dir:
        hidden_dir = Path(temp_dir)
        try:
            hidden_paths = _write_hidden_eval_tests(hidden_dir, hidden_specs)
        except ValueError as exc:
            return False, str(exc)
        if not hidden_paths:
            return True, ""
        return _run_pytest_targets(workspace, hidden_paths, use_docker)


def _write_hidden_eval_tests(
    hidden_dir: Path, hidden_specs: dict[str, ParsedSpec]
) -> list[Path]:
    """Write hidden eval tests to temporary files and return file paths.

    Args:
        hidden_dir: Temporary directory to write hidden test files into.
        hidden_specs: Mapping of function name to spec with hidden evals.

    Returns:
        List of paths to written hidden test files.
    """
    written_paths = []
    for func_name, function_spec in hidden_specs.items():
        test_path = hidden_dir / f"test_hidden_{func_name}.py"
        test_path.write_text(
            _build_hidden_eval_test_source(function_spec),
            encoding="utf-8",
        )
        written_paths.append(test_path)
    return written_paths


def _build_hidden_eval_test_source(spec: ParsedSpec) -> str:
    """Build hidden pytest source for one function spec.

    Args:
        spec: Function-scoped ParsedSpec containing hidden evals.

    Returns:
        Python source code string for hidden eval test cases.
    """
    module_candidates = _module_candidates_from_targets(spec.target_files)
    if not module_candidates:
        raise ValueError(
            "HIDDEN EVAL CONFIG ERROR: Could not derive import module candidates "
            f"for function '{spec.name}' from target_files={spec.target_files!r}. "
            "Provide Python source file paths in target_files."
        )
    lines = [
        "import importlib",
        "",
        f"FUNCTION_NAME = {spec.name!r}",
        f"MODULE_CANDIDATES = {module_candidates!r}",
        "",
        "def _load_target():",
        "    for module_name in MODULE_CANDIDATES:",
        "        try:",
        "            module = importlib.import_module(module_name)",
        "        except Exception:",
        "            continue",
        "        if hasattr(module, FUNCTION_NAME):",
        "            return getattr(module, FUNCTION_NAME)",
        "    raise AssertionError('Could not import target function for hidden evals')",
        "",
        "TARGET_FUNC = _load_target()",
        "",
    ]
    for idx, case in enumerate(spec.hidden_evals):
        lines.append(f"def test_hidden_case_{idx}():")
        lines.append(f"    assert TARGET_FUNC{case['input']} == {case['output']}")
        lines.append("")
    return "\n".join(lines)


def _module_candidates_from_targets(target_files: list[str]) -> list[str]:
    """Build import-module candidates from configured target file paths.

    Args:
        target_files: List of target file path strings from the spec.

    Returns:
        List of Python module name candidates for dynamic import.
    """
    candidates: list[str] = []
    for raw_path in target_files:
        path = Path(raw_path)
        if path.suffix != ".py":
            continue
        parts = list(path.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        _append_unique(candidates, ".".join(parts))
        _append_unique(candidates, parts[-1])
        if len(parts) > 1 and parts[0] in {"src", "app", "lib"}:
            _append_unique(candidates, ".".join(parts[1:]))
    return candidates


def _append_unique(items: list[str], value: str) -> None:
    """Append value if it does not already exist.

    Args:
        items: Target list to append to.
        value: String value to append if not already present.
    """
    if value and value not in items:
        items.append(value)


def _redacted_hidden_failure_feedback(
    hidden_output: str, hidden_specs: dict[str, ParsedSpec]
) -> str:
    """Return non-sensitive feedback text for hidden eval failures.

    Args:
        hidden_output: Raw pytest output from hidden eval runs.
        hidden_specs: Mapping of function name to spec with hidden evals.

    Returns:
        Redacted feedback string safe to show to the implementation agent.
    """
    failed_cases = _count_failed_cases(hidden_output)
    function_count = len(hidden_specs)
    return (
        f"Hidden evaluations failed ({failed_cases} case(s) across "
        f"{function_count} function(s)). Hidden details are redacted. "
        "Generalize your implementation and handle broader inputs."
    )


def _format_agent_failure_feedback(
    returncode: int,
    stdout: str,
    stderr: str,
    max_chars: int = 1200,
) -> str:
    """Format bounded feedback for implementation-agent command failures.

    Args:
        returncode: Process exit code from the implementation agent.
        stdout: Agent process stdout.
        stderr: Agent process stderr.
        max_chars: Maximum characters to include for each stream.

    Returns:
        Retry feedback string including bounded process output.
    """
    parts = [f"IMPLEMENTATION AGENT FAILED (exit code {returncode})."]
    stderr_excerpt = _bounded_excerpt(stderr, max_chars)
    stdout_excerpt = _bounded_excerpt(stdout, max_chars)
    if stderr_excerpt:
        parts.append(f"stderr:\n{stderr_excerpt}")
    if stdout_excerpt:
        parts.append(f"stdout:\n{stdout_excerpt}")
    parts.append("Fix the failure and retry implementation.")
    return "\n\n".join(parts)


def _bounded_excerpt(text: str, limit: int) -> str:
    """Trim and bound text size for retry feedback.

    Args:
        text: Raw process output text.
        limit: Max number of characters to keep.

    Returns:
        Bounded excerpt, preserving the end marker when truncated.
    """
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "\n...[truncated]..."


def _count_failed_cases(pytest_output: str) -> int:
    """Count failing pytest cases from output without exposing payloads.

    Args:
        pytest_output: Raw pytest stdout/stderr output.

    Returns:
        Number of failed test cases, minimum 1.
    """
    count = 0
    for line in pytest_output.splitlines():
        if line.startswith("FAILED "):
            count += 1
    return count if count > 0 else 1


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
            public_evals = function_spec.public_evals or spec.public_evals
            hidden_evals = function_spec.hidden_evals or spec.hidden_evals
            return ParsedSpec(
                name=function_spec.name,
                description=function_spec.description or spec.description,
                examples=list(public_evals),
                public_evals=list(public_evals),
                hidden_evals=list(hidden_evals),
                signature=function_spec.signature or spec.signature,
                constraint_profile=function_spec.constraint_profile
                or spec.constraint_profile,
                target_files=list(spec.target_files),
                functions=list(spec.functions),
            )
    return ParsedSpec(
        name=func_name,
        description=spec.description,
        examples=list(spec.public_evals),
        public_evals=list(spec.public_evals),
        hidden_evals=list(spec.hidden_evals),
        signature=spec.signature,
        constraint_profile=spec.constraint_profile,
        target_files=list(spec.target_files),
        functions=list(spec.functions),
    )


def _format_critique_feedback(critique: TestCritique) -> str:
    """Format a critique into feedback text for the generation prompt.

    Args:
        critique: Structured critique from the critic.

    Returns:
        Formatted feedback string summarizing critic findings.
    """
    parts = []
    if critique.missing_edge_cases:
        parts.append("Missing edge cases to add (pick the most important):")
        parts.extend(f"  - {c}" for c in critique.missing_edge_cases[:5])
    if critique.exploit_passed:
        parts.append("Warning: a cheating implementation passed your tests.")
        parts.append("Add tests with dynamic/random inputs to prevent hardcoding.")
    return "\n".join(parts)


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
