"""Generate an implementation plan from session state and spec."""

from pathlib import Path

from orchestrator.models import (
    FunctionStatus,
    ParsedSpec,
    SessionState,
    TaskConstraints,
)


def build_implementation_plan(
    state: SessionState,
    spec: ParsedSpec,
    constraints_map: dict[str, TaskConstraints],
) -> str:
    """Build a structured markdown implementation plan.

    Iterates over completed functions in the session and formats their
    signatures, descriptions, public evals, constraints, and critique findings
    into a plan document for the implementation agent.

    Args:
        state: Session state with per-function progress and critique.
        spec: Parsed task specification with function details.
        constraints_map: Map of function name to resolved constraints.

    Returns:
        Markdown string containing the full implementation plan.
    """
    sections = [f"# Implementation Plan\n\n## Project: {spec.name}\n"]
    sections.append(f"**Description:** {spec.description}\n")

    if spec.target_files:
        sections.append("## Target Files\n")
        for path in spec.target_files:
            sections.append(f"- `{path}`")
        sections.append("")

    sections.append("## Test Files\n")
    for progress in state.function_progress:
        if progress.test_source:
            sections.append(f"- `tests/test_{progress.name}.py`")
    sections.append("")

    sections.append("## Functions\n")

    func_lookup = {f.name: f for f in spec.functions}

    for progress in state.function_progress:
        if progress.status != FunctionStatus.done:
            continue
        func_spec = func_lookup.get(progress.name)
        sections.append(f"### {progress.name}\n")

        if func_spec and func_spec.signature:
            sections.append(f"**Signature:** `{func_spec.signature}`\n")
        elif spec.signature:
            sections.append(f"**Signature:** `{spec.signature}`\n")

        description = (func_spec.description if func_spec else "") or spec.description
        sections.append(f"**Description:** {description}\n")

        public_evals = (func_spec.public_evals if func_spec else []) or spec.public_evals
        if public_evals:
            sections.append("**Public evals:**")
            for ex in public_evals:
                if "input" in ex:
                    sections.append(
                        f"- `{progress.name}({ex['input']})` -> `{ex.get('output', '?')}`"
                    )
                elif "raw" in ex:
                    sections.append(f"- {ex['raw']}")
            sections.append("")

        constraints = constraints_map.get(progress.name)
        if constraints:
            sections.append("**Constraints:**")
            _append_constraints(sections, constraints)
            sections.append("")

        if progress.critique:
            sections.append("**Critique findings:**")
            _append_critique(sections, progress.critique)
            sections.append("")

        sections.append("---\n")

    return "\n".join(sections)


def write_plan_to_workspace(plan_content: str, workspace: Path) -> Path:
    """Write a plan string to ``plan.md`` inside the workspace directory.

    Args:
        plan_content: Markdown plan text.
        workspace: Directory to write the plan file into.

    Returns:
        Path to the written ``plan.md`` file.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    plan_path = workspace / "plan.md"
    plan_path.write_text(plan_content, encoding="utf-8")
    return plan_path


def _append_constraints(
    sections: list[str], constraints: TaskConstraints
) -> None:
    """Append constraint bullet points to *sections*.

    Dynamically iterates over all fields in both primary and secondary
    ConstraintSet objects, emitting a bullet for every non-None value.

    Args:
        sections: List of markdown lines being built.
        constraints: Resolved constraints for a function.
    """
    for label, cset in [("primary", constraints.primary),
                        ("secondary", constraints.secondary)]:
        constraint_items = cset.model_dump(exclude_none=True)
        if not constraint_items:
            continue
        sections.append(f"- {label} constraints:")
        for field_name, value in constraint_items.items():
            readable = field_name.replace("_", " ")
            if isinstance(value, bool):
                sections.append(f"  - {readable}: {'yes' if value else 'no'}")
            elif isinstance(value, list):
                sections.append(f"  - {readable}: {', '.join(str(v) for v in value)}")
            else:
                sections.append(f"  - {readable}: {value}")
    if constraints.guidance:
        for item in constraints.guidance:
            sections.append(f"- {item}")


def _append_critique(sections: list[str], critique) -> None:
    """Append critique findings as bullet points to *sections*.

    Args:
        sections: List of markdown lines being built.
        critique: TestCritique from the completed function.
    """
    if critique.exploit_vectors:
        sections.append("- Exploit vectors:")
        for v in critique.exploit_vectors:
            sections.append(f"  - {v}")
    if critique.missing_edge_cases:
        sections.append("- Missing edge cases:")
        for c in critique.missing_edge_cases:
            sections.append(f"  - {c}")
    if critique.suggested_counter_tests:
        sections.append("- Suggested counter-tests:")
        for t in critique.suggested_counter_tests:
            sections.append(f"  - {t}")
