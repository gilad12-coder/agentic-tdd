from pathlib import Path

import pytest



@pytest.fixture
def minimal_spec():
    """Provide a minimal ParsedSpec for testing.

    Returns:
        ParsedSpec with name "add" and basic examples.
    """
    from orchestrator.models import ParsedSpec

    return ParsedSpec(
        name="add",
        description="Add two integers and return their sum",
        examples=[
            {"input": "(1, 2)", "output": "3"},
            {"input": "(0, 0)", "output": "0"},
            {"input": "(-1, 1)", "output": "0"},
        ],
        signature="(a: int, b: int) -> int",
        constraint_profile="strict",
    )


@pytest.fixture
def minimal_constraints():
    """Provide minimal TaskConstraints for testing.

    Returns:
        TaskConstraints with basic primary and secondary constraints.
    """
    from orchestrator.models import ConstraintSet, TaskConstraints

    return TaskConstraints(
        primary=ConstraintSet(
            max_cyclomatic_complexity=5,
            max_lines_per_function=30,
        ),
        secondary=ConstraintSet(
            require_docstrings=True,
        ),
        target_files=["src/add.py"],
    )


@pytest.fixture
def orchestrator_constraints_path():
    """Provide the path to the orchestrator constraints YAML file.

    Returns:
        Path to constraints/orchestrator.yaml.
    """
    return Path(__file__).parent.parent / "constraints" / "orchestrator.yaml"
