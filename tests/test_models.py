import pytest
from pydantic import ValidationError

from orchestrator.models import (
    CLIResult,
    ConstraintResult,
    ConstraintSet,
    FunctionSpec,
    ParsedSpec,
    TaskConstraints,
    TestCritique,
)


# --- ConstraintSet ---


class TestConstraintSet:
    """Tests for ConstraintSet."""

    def test_constraint_set_all_fields_optional(self):
        """Test that all ConstraintSet fields default to None."""
        cs = ConstraintSet()
        assert cs.max_cyclomatic_complexity is None
        assert cs.max_lines_per_function is None
        assert cs.max_total_lines is None
        assert cs.require_docstrings is None
        assert cs.allowed_imports is None

    def test_constraint_set_rejects_invalid_values(self):
        """Test that ConstraintSet rejects negative or zero values."""
        with pytest.raises(ValidationError):
            ConstraintSet(max_cyclomatic_complexity=-1)
        with pytest.raises(ValidationError):
            ConstraintSet(max_lines_per_function=0)

    def test_constraint_set_accepts_valid_values(self):
        """Test that ConstraintSet accepts valid constraint values."""
        cs = ConstraintSet(
            max_cyclomatic_complexity=5,
            max_lines_per_function=50,
            max_total_lines=200,
            require_docstrings=True,
            allowed_imports=["os", "sys"],
        )
        assert cs.max_cyclomatic_complexity == 5
        assert cs.max_lines_per_function == 50
        assert cs.allowed_imports == ["os", "sys"]

    def test_constraint_set_allowed_imports_list(self):
        """Test that allowed_imports stores a list of strings."""
        cs = ConstraintSet(allowed_imports=["os", "pathlib"])
        assert isinstance(cs.allowed_imports, list)
        assert all(isinstance(i, str) for i in cs.allowed_imports)


# --- TaskConstraints ---


class TestTaskConstraints:
    """Tests for TaskConstraints."""

    def test_task_constraints_has_primary_and_secondary(self):
        """Test that TaskConstraints has primary and secondary ConstraintSets."""
        tc = TaskConstraints(
            primary=ConstraintSet(max_cyclomatic_complexity=5),
            secondary=ConstraintSet(require_docstrings=True),
            target_files=["src/main.py"],
        )
        assert isinstance(tc.primary, ConstraintSet)
        assert isinstance(tc.secondary, ConstraintSet)

    def test_task_constraints_has_target_files(self):
        """Test that TaskConstraints stores target file paths."""
        tc = TaskConstraints(
            primary=ConstraintSet(),
            secondary=ConstraintSet(),
            target_files=["src/a.py", "src/b.py"],
        )
        assert tc.target_files == ["src/a.py", "src/b.py"]

    def test_task_constraints_from_dict(self):
        """Test that TaskConstraints can be constructed from a dict."""
        data = {
            "primary": {"max_cyclomatic_complexity": 10},
            "secondary": {"require_docstrings": True},
            "target_files": ["src/main.py"],
        }
        tc = TaskConstraints(**data)
        assert tc.primary.max_cyclomatic_complexity == 10
        assert tc.secondary.require_docstrings is True

    def test_task_constraints_empty_sections_valid(self):
        """Test that TaskConstraints accepts empty constraint sections."""
        tc = TaskConstraints(
            primary=ConstraintSet(),
            secondary=ConstraintSet(),
            target_files=[],
        )
        assert tc.primary.max_cyclomatic_complexity is None
        assert tc.secondary.require_docstrings is None

    def test_task_constraints_same_type_in_both(self):
        """Test that the same constraint type can appear in both sections."""
        tc = TaskConstraints(
            primary=ConstraintSet(max_cyclomatic_complexity=5),
            secondary=ConstraintSet(max_cyclomatic_complexity=3),
            target_files=[],
        )
        assert tc.primary.max_cyclomatic_complexity == 5
        assert tc.secondary.max_cyclomatic_complexity == 3


# --- CLIResult ---


class TestCLIResult:
    """Tests for CLIResult."""

    def test_cli_result_stores_all_fields(self):
        """Test that CLIResult stores stdout, stderr, exit_code, and parsed_json."""
        result = CLIResult(
            stdout="hello world",
            stderr="",
            exit_code=0,
            parsed_json={"key": "value"},
        )
        assert isinstance(result.stdout, str)
        assert isinstance(result.stderr, str)
        assert isinstance(result.exit_code, int)
        assert result.parsed_json == {"key": "value"}

    def test_cli_result_parsed_json_optional(self):
        """Test that CLIResult allows parsed_json to be None."""
        result = CLIResult(stdout="text", stderr="", exit_code=0, parsed_json=None)
        assert result.parsed_json is None


# --- ParsedSpec ---


class TestFunctionSpec:
    """Tests for FunctionSpec."""

    def test_function_spec_optional_fields(self):
        """Test that FunctionSpec optional fields have sensible defaults."""
        fs = FunctionSpec(name="logout")
        assert fs.description == ""
        assert fs.signature is None
        assert fs.examples == []
        assert fs.public_evals == []
        assert fs.hidden_evals == []
        assert fs.constraint_profile is None

    def test_function_spec_examples_aliases_to_public_evals(self):
        """Test that examples are normalized into public_evals."""
        fs = FunctionSpec(
            name="logout",
            examples=[{"input": '("abc")', "output": "True"}],
        )
        assert fs.public_evals == [{"input": '("abc")', "output": "True"}]
        assert fs.examples == fs.public_evals

    def test_function_spec_public_evals_override_examples(self):
        """Test that explicit public_evals wins over examples."""
        fs = FunctionSpec(
            name="logout",
            examples=[{"input": '("abc")', "output": "False"}],
            public_evals=[{"input": '("abc")', "output": "True"}],
        )
        assert fs.public_evals == [{"input": '("abc")', "output": "True"}]
        assert fs.examples == fs.public_evals

    def test_function_spec_hidden_evals_schema_validation(self):
        """Test that hidden_evals enforce input/output and ban raw."""
        with pytest.raises(ValidationError):
            FunctionSpec(name="logout", hidden_evals=[{"input": "(1)"}])
        with pytest.raises(ValidationError):
            FunctionSpec(name="logout", hidden_evals=[{"raw": "foo"}])
        with pytest.raises(ValidationError):
            FunctionSpec(name="logout", hidden_evals=[{"input": 1, "output": "2"}])

    def test_function_spec_hidden_input_expression_validation(self):
        """Test that malformed hidden input expressions are rejected."""
        with pytest.raises(ValidationError):
            FunctionSpec(
                name="logout",
                hidden_evals=[{"input": "(1, 2", "output": "3"}],
            )

    def test_function_spec_hidden_output_expression_validation(self):
        """Test that malformed hidden output expressions are rejected."""
        with pytest.raises(ValidationError):
            FunctionSpec(
                name="logout",
                hidden_evals=[{"input": "(1, 2)", "output": "3 +"}],
            )


class TestParsedSpec:
    """Tests for ParsedSpec."""

    def test_parsed_spec_required_fields(self):
        """Test that ParsedSpec stores required fields correctly."""
        spec = ParsedSpec(
            name="is_palindrome",
            description="Check if string is palindrome",
            examples=[{"input": '"racecar"', "output": "True"}],
        )
        assert spec.name == "is_palindrome"
        assert spec.description == "Check if string is palindrome"
        assert len(spec.examples) == 1
        assert spec.public_evals == spec.examples

    def test_parsed_spec_required_fields_missing(self):
        """Test that ParsedSpec raises when required fields are missing."""
        with pytest.raises(ValidationError):
            ParsedSpec(name="test")  # type: ignore[call-arg]

    def test_parsed_spec_optional_fields(self):
        """Test that ParsedSpec stores optional fields when provided."""
        spec = ParsedSpec(
            name="add",
            description="Add two numbers",
            examples=[],
            signature="(a: int, b: int) -> int",
        )
        assert spec.signature == "(a: int, b: int) -> int"

    def test_parsed_spec_optional_fields_default(self):
        """Test that ParsedSpec optional fields default to None."""
        spec = ParsedSpec(
            name="add",
            description="Add two numbers",
            examples=[],
        )
        assert spec.signature is None

    def test_parsed_spec_constraint_profile_default(self):
        """Test that ParsedSpec defaults to the 'default' constraint profile."""
        spec = ParsedSpec(
            name="add",
            description="Add two numbers",
            examples=[],
        )
        assert spec.constraint_profile == "default"

    def test_parsed_spec_target_files_default(self):
        """Test that ParsedSpec defaults to an empty target files list."""
        spec = ParsedSpec(
            name="add",
            description="Add two numbers",
            examples=[],
        )
        assert spec.target_files == []

    def test_parsed_spec_functions_list(self):
        """Test that ParsedSpec stores a list of FunctionSpec objects."""
        spec = ParsedSpec(
            name="auth_system",
            description="Auth module",
            examples=[],
            functions=[
                FunctionSpec(name="login", description="Log in"),
                FunctionSpec(name="logout", description="Log out"),
            ],
        )
        assert len(spec.functions) == 2
        assert spec.functions[0].name == "login"
        assert spec.functions[1].name == "logout"

    def test_parsed_spec_functions_default(self):
        """Test that ParsedSpec defaults to an empty functions list."""
        spec = ParsedSpec(
            name="add",
            description="Add two numbers",
            examples=[],
        )
        assert spec.functions == []

    def test_parsed_spec_public_evals_override_examples(self):
        """Test that top-level public_evals takes precedence over examples."""
        spec = ParsedSpec(
            name="add",
            description="Add two numbers",
            examples=[{"input": "(1, 1)", "output": "2"}],
            public_evals=[{"input": "(2, 2)", "output": "4"}],
        )
        assert spec.public_evals == [{"input": "(2, 2)", "output": "4"}]
        assert spec.examples == spec.public_evals

    def test_parsed_spec_hidden_eval_validation(self):
        """Test that ParsedSpec hidden evals require string input/output."""
        with pytest.raises(ValidationError):
            ParsedSpec(
                name="add",
                description="Add two numbers",
                hidden_evals=[{"input": "(1, 2)", "output": 3}],
            )


# --- TestCritique ---


class TestTestCritique:
    """Tests for TestCritique."""

    def test_test_critique_stores_string_lists(self):
        """Test that TestCritique stores lists of strings for all fields."""
        critique = TestCritique(
            exploit_vectors=["hardcode return values"],
            missing_edge_cases=["empty input"],
            suggested_counter_tests=["def test_counter(): assert add(-1, -1) == -2"],
        )
        assert isinstance(critique.exploit_vectors, list)
        assert isinstance(critique.missing_edge_cases, list)
        assert isinstance(critique.suggested_counter_tests, list)
        assert all(isinstance(v, str) for v in critique.exploit_vectors)
        assert all(isinstance(v, str) for v in critique.missing_edge_cases)
        assert all(isinstance(v, str) for v in critique.suggested_counter_tests)

    def test_test_critique_exploit_fields_optional(self):
        """Test that TestCritique exploit fields have sensible defaults."""
        critique = TestCritique(
            exploit_vectors=["cheat"],
            missing_edge_cases=[],
            suggested_counter_tests=[],
        )
        assert critique.exploit_code is None
        assert critique.exploit_passed is False

        critique_with = TestCritique(
            exploit_vectors=[],
            missing_edge_cases=[],
            suggested_counter_tests=[],
            exploit_code="def add(a, b): return 3",
            exploit_passed=True,
        )
        assert critique_with.exploit_code == "def add(a, b): return 3"
        assert critique_with.exploit_passed is True


# --- ConstraintResult ---


class TestConstraintResult:
    """Tests for ConstraintResult."""

    def test_constraint_result_stores_violations_and_metrics(self):
        """Test that ConstraintResult stores violations and metrics."""
        result = ConstraintResult(
            passed=False,
            violations=["cyclomatic complexity 12 > max 10"],
            metrics={"cyclomatic_complexity": 12, "lines_per_function": 45},
        )
        assert result.passed is False
        assert isinstance(result.violations, list)
        assert isinstance(result.metrics, dict)
        assert "cyclomatic_complexity" in result.metrics

    def test_constraint_result_passing(self):
        """Test that a passing ConstraintResult has no violations."""
        result = ConstraintResult(passed=True, violations=[], metrics={})
        assert result.passed is True
        assert result.violations == []
