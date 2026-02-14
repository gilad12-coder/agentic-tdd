"""Tests for the plan generator module."""

from orchestrator.models import (
    ConstraintSet,
    FunctionProgress,
    FunctionSpec,
    FunctionStatus,
    ParsedSpec,
    SessionState,
    TaskConstraints,
    TestCritique,
)
from orchestrator.plan_generator import (
    build_implementation_plan,
    write_plan_to_workspace,
)


def _make_spec():
    """Create a multi-function ParsedSpec for testing.

    Returns:
        ParsedSpec with two functions.
    """
    return ParsedSpec(
        name="calculator",
        description="A simple calculator",
        target_files=["src/calc.py"],
        functions=[
            FunctionSpec(
                name="add",
                description="Add two numbers",
                signature="add(a: int, b: int) -> int",
                examples=[{"input": "(1, 2)", "output": "3"}],
            ),
            FunctionSpec(
                name="subtract",
                description="Subtract two numbers",
                signature="subtract(a: int, b: int) -> int",
                examples=[{"input": "(5, 3)", "output": "2"}],
            ),
        ],
    )


def _make_constraints_map():
    """Create a constraints map for testing.

    Returns:
        Dict mapping function names to TaskConstraints.
    """
    return {
        "add": TaskConstraints(
            primary=ConstraintSet(max_cyclomatic_complexity=5),
            secondary=ConstraintSet(require_docstrings=True),
            target_files=["src/calc.py"],
        ),
        "subtract": TaskConstraints(
            primary=ConstraintSet(max_lines_per_function=30),
            secondary=ConstraintSet(no_print_statements=True),
            target_files=["src/calc.py"],
        ),
    }


def _make_state():
    """Create a session state with completed functions.

    Returns:
        SessionState with two done functions including critiques.
    """
    return SessionState(
        function_progress=[
            FunctionProgress(
                name="add",
                status=FunctionStatus.done,
                test_source="def test_add(): assert add(1, 2) == 3",
                critique=TestCritique(
                    exploit_vectors=["hardcode return 3"],
                    missing_edge_cases=["negative numbers"],
                    suggested_counter_tests=["test_negative"],
                ),
            ),
            FunctionProgress(
                name="subtract",
                status=FunctionStatus.done,
                test_source="def test_sub(): assert subtract(5, 3) == 2",
                critique=TestCritique(
                    exploit_vectors=[],
                    missing_edge_cases=["zero"],
                    suggested_counter_tests=[],
                ),
            ),
        ]
    )


# --- build_implementation_plan ---


class TestBuildImplementationPlan:
    """Tests for build_implementation_plan."""

    def test_contains_project_name(self):
        """Test that the plan contains the project name."""
        plan = build_implementation_plan(
            _make_state(), _make_spec(), _make_constraints_map()
        )
        assert "calculator" in plan

    def test_contains_function_names(self):
        """Test that the plan contains function names."""
        plan = build_implementation_plan(
            _make_state(), _make_spec(), _make_constraints_map()
        )
        assert "### add" in plan
        assert "### subtract" in plan

    def test_contains_signatures(self):
        """Test that the plan contains function signatures."""
        plan = build_implementation_plan(
            _make_state(), _make_spec(), _make_constraints_map()
        )
        assert "add(a: int, b: int) -> int" in plan
        assert "subtract(a: int, b: int) -> int" in plan

    def test_contains_descriptions(self):
        """Test that the plan contains function descriptions."""
        plan = build_implementation_plan(
            _make_state(), _make_spec(), _make_constraints_map()
        )
        assert "Add two numbers" in plan
        assert "Subtract two numbers" in plan

    def test_contains_examples(self):
        """Test that the plan contains spec examples."""
        plan = build_implementation_plan(
            _make_state(), _make_spec(), _make_constraints_map()
        )
        assert "(1, 2)" in plan
        assert "(5, 3)" in plan

    def test_contains_constraints(self):
        """Test that the plan contains constraint information."""
        plan = build_implementation_plan(
            _make_state(), _make_spec(), _make_constraints_map()
        )
        assert "cyclomatic complexity" in plan.lower()
        assert "docstrings" in plan.lower()

    def test_contains_target_files(self):
        """Test that the plan contains target file paths."""
        plan = build_implementation_plan(
            _make_state(), _make_spec(), _make_constraints_map()
        )
        assert "src/calc.py" in plan

    def test_contains_critique_findings(self):
        """Test that the plan contains critique findings."""
        plan = build_implementation_plan(
            _make_state(), _make_spec(), _make_constraints_map()
        )
        assert "hardcode return 3" in plan
        assert "negative numbers" in plan

    def test_skips_pending_functions(self):
        """Test that pending functions are not included in the plan."""
        state = SessionState(
            function_progress=[
                FunctionProgress(name="add", status=FunctionStatus.done,
                                 test_source="code"),
                FunctionProgress(name="pending_fn", status=FunctionStatus.pending),
            ]
        )
        plan = build_implementation_plan(state, _make_spec(), _make_constraints_map())
        assert "### add" in plan
        assert "pending_fn" not in plan

    def test_empty_state(self):
        """Test that empty state produces a plan with no function sections."""
        state = SessionState(function_progress=[])
        plan = build_implementation_plan(state, _make_spec(), _make_constraints_map())
        assert "Implementation Plan" in plan
        assert "### " not in plan

    def test_no_critique(self):
        """Test that functions without critique are handled gracefully."""
        state = SessionState(
            function_progress=[
                FunctionProgress(
                    name="add",
                    status=FunctionStatus.done,
                    test_source="code",
                    critique=None,
                ),
            ]
        )
        plan = build_implementation_plan(state, _make_spec(), _make_constraints_map())
        assert "### add" in plan
        assert "Exploit vectors" not in plan


# --- write_plan_to_workspace ---


class TestWritePlanToWorkspace:
    """Tests for write_plan_to_workspace."""

    def test_writes_file(self, tmp_path):
        """Test that plan.md is written to the workspace.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        plan_path = write_plan_to_workspace("# Test Plan", tmp_path)
        assert plan_path.exists()
        assert plan_path.name == "plan.md"
        assert plan_path.read_text() == "# Test Plan"

    def test_creates_workspace_directory(self, tmp_path):
        """Test that the workspace directory is created if missing.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        nested = tmp_path / "deep" / "dir"
        plan_path = write_plan_to_workspace("content", nested)
        assert plan_path.exists()

    def test_returns_correct_path(self, tmp_path):
        """Test that the returned path points to plan.md.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        plan_path = write_plan_to_workspace("content", tmp_path)
        assert plan_path == tmp_path / "plan.md"
