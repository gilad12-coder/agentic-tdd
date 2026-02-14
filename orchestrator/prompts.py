"""LLM prompt builders for test generation, critique, and implementation."""

from pathlib import Path

from orchestrator.models import ParsedSpec, TaskConstraints


def build_generation_prompt(
    spec: ParsedSpec,
    constraints: TaskConstraints,
    constraint_feedback: str = "",
    critique_feedback: str = "",
) -> str:
    """Build a prompt string for generating pytest tests from a spec.

    Args:
        spec: ParsedSpec with function details.
        constraints: TaskConstraints with primary and secondary gates.
        constraint_feedback: Violations from a previous attempt to fix on retry.
        critique_feedback: Critic findings from a previous cycle to address.

    Returns:
        Prompt string for test generation.
    """
    examples_str = _format_examples(spec)
    primary_str = _format_primary_constraints(constraints)
    secondary_str = _format_secondary_constraints(constraints)
    guidance_str = _format_guidance(constraints)

    prompt = (
        f"Write pytest tests for the function `{spec.name}`.\n\n"
        f"Description: {spec.description}\n\n"
        f"Signature: {spec.signature or 'not specified'}\n\n"
        f"Examples:\n{examples_str}\n"
        f"Primary constraints:\n{primary_str}\n\n"
        f"Secondary constraints:\n{secondary_str}\n\n"
        f"Guidance:\n{guidance_str}\n\n"
        f"Generate comprehensive pytest test functions that cover edge cases.\n\n"
        f"IMPORTANT: Output ONLY the complete Python test file content in a single "
        f"```python``` code block. Do NOT write any files to disk. Do NOT read any "
        f"existing files. Just output the test code."
    )

    if constraint_feedback:
        prompt += (
            f"\n\nWARNING: A previous generation was rejected for these constraint "
            f"violations. You MUST fix ALL of them:\n{constraint_feedback}"
        )

    if critique_feedback:
        prompt += (
            f"\n\nCRITIC FEEDBACK: A previous version of these tests was reviewed "
            f"by a red-team critic and found to be weak. You MUST address these "
            f"findings in your new tests:\n{critique_feedback}"
        )

    return prompt


def build_critic_prompt(
    test_source: str,
    spec: ParsedSpec,
    constraints: TaskConstraints | None = None,
) -> str:
    """Build an adversarial prompt to review test code for exploitability.

    Args:
        test_source: Source code of test functions.
        spec: ParsedSpec with function details.
        constraints: Optional constraints and guidance for the critique.

    Returns:
        Prompt string for critique.
    """
    constraints_section = _format_constraints_section(constraints)
    examples_str = _format_examples(spec)
    return (
        f"You are a red-team critic. Review the following test code for the "
        f"function `{spec.name}` and find ways to exploit or game it.\n\n"
        f"Test code:\n```python\n{test_source}\n```\n\n"
        f"Specification: {spec.description}\n\n"
        f"Signature: {spec.signature or 'not specified'}\n\n"
        f"Examples:\n{examples_str}\n\n"
        f"{constraints_section}"
        f"Identify ways an implementation could cheat or exploit these tests "
        f"by passing them without truly implementing the specification.\n\n"
        f"Also evaluate whether the tests adequately enforce the stated "
        f"constraints and guidance.\n\n"
        f"Respond with ONLY a JSON object (no markdown fences, no explanation) "
        f"with exactly these fields:\n"
        f'{{"exploit_vectors": ["string", ...], '
        f'"missing_edge_cases": ["string", ...], '
        f'"suggested_counter_tests": ["string", ...]}}\n\n'
        f"Each value must be a flat list of plain strings, NOT dicts or objects.\n"
    )


def build_exploit_prompt(test_source: str, spec: ParsedSpec) -> str:
    """Build a prompt asking for a deliberately cheating implementation.

    Args:
        test_source: Generated test suite source code.
        spec: ParsedSpec with function details and examples.

    Returns:
        Prompt instructing the model to write exploit code only.
    """
    examples_str = _format_examples(spec)
    return (
        f"You are an adversarial engineer trying to cheat tests.\n\n"
        f"Write the weakest possible implementation for `{spec.name}` that "
        f"passes the tests below while violating the true intent of the spec "
        f"when possible.\n\n"
        f"Function spec:\n"
        f"- Name: {spec.name}\n"
        f"- Description: {spec.description}\n"
        f"- Signature: {spec.signature or 'not specified'}\n"
        f"- Examples:\n{examples_str}\n\n"
        f"Tests to exploit:\n```python\n{test_source}\n```\n\n"
        f"Return only Python code for the implementation. Do not include "
        f"Markdown fences or explanations."
    )


def build_implementation_prompt(
    test_paths: list[Path],
    plan_path: Path | None = None,
    error_feedback: str = "",
) -> str:
    """Build the implementation prompt from generated test file paths.

    Args:
        test_paths: Generated test files that define target behavior.
        plan_path: Optional path to a plan.md with context for the agent.
        error_feedback: Pytest error output from a previous failed attempt.

    Returns:
        Prompt instructing the implementation agent what to do.
    """
    if not test_paths:
        return "No generated tests were provided. Make no changes."
    files = ", ".join(str(path) for path in test_paths)
    parts = []
    if plan_path:
        parts.append(
            f"Read the implementation plan at {plan_path} for full context "
            f"on function signatures, constraints, and critique findings."
        )
    parts.append(
        f"Implement production code so all generated tests pass. "
        f"Use these tests: {files}."
    )
    parts.append(
        "Write your implementation to the target files specified in the plan. "
        "Run pytest to verify your implementation passes all tests before finishing."
    )
    if error_feedback:
        parts.append(
            f"\nPREVIOUS ATTEMPT FAILED. Fix the errors below:\n{error_feedback}"
        )
    return "\n\n".join(parts)


# --- Private formatting helpers ---


def _format_examples(spec: ParsedSpec) -> str:
    """Format spec examples into a prompt section.

    Args:
        spec: ParsedSpec containing example input/output pairs.

    Returns:
        Formatted examples string.
    """
    parts = []
    for ex in spec.examples:
        if "input" in ex:
            parts.append(f"  - {spec.name}({ex['input']}) -> {ex.get('output', '?')}")
        elif "raw" in ex:
            parts.append(f"  - {ex['raw']}")
    return "\n".join(parts)


def _format_primary_constraints(constraints: TaskConstraints) -> str:
    """Format primary constraints into a prompt section.

    Args:
        constraints: TaskConstraints with primary gate values.

    Returns:
        Formatted primary constraints string.
    """
    parts = []
    if constraints.primary.max_cyclomatic_complexity is not None:
        parts.append(
            f"max cyclomatic complexity: {constraints.primary.max_cyclomatic_complexity}"
        )
    if constraints.primary.max_lines_per_function is not None:
        parts.append(
            f"max lines per function: {constraints.primary.max_lines_per_function}"
        )
    if constraints.primary.max_time_complexity is not None:
        parts.append(
            f"max time complexity: {constraints.primary.max_time_complexity}"
        )
    return "\n".join(f"  - {p}" for p in parts) if parts else "  (none)"


def _format_secondary_constraints(constraints: TaskConstraints) -> str:
    """Format secondary constraints into a prompt section.

    Args:
        constraints: TaskConstraints with secondary gate values.

    Returns:
        Formatted secondary constraints string.
    """
    parts = []
    if constraints.secondary.require_docstrings:
        parts.append(
            "EVERY function and class must have a docstring. Example:\n"
            "    def test_example(self):\n"
            '        """Verify example behavior."""\n'
            "        assert func(1) == 2"
        )
    if constraints.secondary.require_type_annotations:
        parts.append("all function parameters and return values must have type annotations")
    if constraints.secondary.no_print_statements:
        parts.append("no print() calls — use logging instead")
    return "\n".join(f"  - {s}" for s in parts) if parts else "  (none)"


def _format_guidance(constraints: TaskConstraints) -> str:
    """Format guidance items into a prompt section.

    Args:
        constraints: TaskConstraints with guidance list.

    Returns:
        Formatted guidance string.
    """
    if constraints.guidance:
        return "\n".join(f"  - {item}" for item in constraints.guidance)
    return "  (none)"


def _format_constraints_section(constraints: TaskConstraints | None) -> str:
    """Format an optional constraints section for the critic prompt.

    Args:
        constraints: Optional resolved constraints for the current task.

    Returns:
        Constraint section text, or an empty string when not provided.
    """
    if constraints is None:
        return ""

    primary_text = _format_primary_constraints(constraints)
    secondary_text = _format_secondary_constraints(constraints)
    guidance_text = _format_guidance(constraints)
    return (
        f"Primary constraints:\n{primary_text}\n\n"
        f"Secondary constraints:\n{secondary_text}\n\n"
        f"Guidance to enforce:\n{guidance_text}\n\n"
    )
