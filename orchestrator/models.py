"""Pydantic v2 models for the orchestrator system."""

import ast
from enum import Enum

from pydantic import BaseModel, Field, model_validator


def _resolve_public_evals(
    examples: list[dict], public_evals: list[dict], fields_set: set[str]
) -> list[dict]:
    """Resolve canonical public evals with explicit precedence rules.

    Args:
        examples: Raw examples from the spec.
        public_evals: Explicit public evals from the spec.
        fields_set: Set of field names explicitly provided by the user.

    Returns:
        Resolved list of public eval dicts.
    """
    if "public_evals" in fields_set:
        return list(public_evals)
    if public_evals:
        return list(public_evals)
    return list(examples)


def _validate_hidden_evals(hidden_evals: list[dict], owner: str) -> None:
    """Validate hidden evals have ``input`` and ``output`` and no ``raw``.

    Args:
        hidden_evals: List of hidden eval dicts to validate.
        owner: Name of the owning model for error messages.
    """
    for idx, item in enumerate(hidden_evals):
        if not isinstance(item, dict):
            raise ValueError(f"{owner}.hidden_evals[{idx}] must be a mapping")
        if "raw" in item:
            raise ValueError(
                f"{owner}.hidden_evals[{idx}] does not support 'raw'; use input/output"
            )
        if "input" not in item or "output" not in item:
            raise ValueError(
                f"{owner}.hidden_evals[{idx}] must contain both 'input' and 'output'"
            )
        if not isinstance(item["input"], str) or not isinstance(item["output"], str):
            raise ValueError(
                f"{owner}.hidden_evals[{idx}] values must be strings"
            )
        try:
            ast.parse(item["input"], mode="eval")
        except SyntaxError as exc:
            raise ValueError(
                f"{owner}.hidden_evals[{idx}].input is not a valid expression: {exc.msg}"
            ) from exc
        try:
            ast.parse(item["output"], mode="eval")
        except SyntaxError as exc:
            raise ValueError(
                f"{owner}.hidden_evals[{idx}].output is not a valid expression: {exc.msg}"
            ) from exc


class ConstraintSet(BaseModel):
    """A set of optional code quality constraints."""

    max_cyclomatic_complexity: int | None = Field(default=None, ge=1)
    max_lines_per_function: int | None = Field(default=None, ge=1)
    max_total_lines: int | None = Field(default=None, ge=1)
    max_time_complexity: str | None = None
    max_parameters: int | None = Field(default=None, ge=0)
    max_nested_depth: int | None = Field(default=None, ge=1)
    max_return_statements: int | None = Field(default=None, ge=1)
    require_docstrings: bool | None = None
    no_print_statements: bool | None = None
    no_star_imports: bool | None = None
    no_mutable_defaults: bool | None = None
    no_global_state: bool | None = None
    allowed_imports: list[str] | None = None
    # Correctness
    no_bare_except: bool | None = None
    no_try_except_pass: bool | None = None
    no_return_in_finally: bool | None = None
    no_unreachable_code: bool | None = None
    no_duplicate_dict_keys: bool | None = None
    no_loop_variable_closure: bool | None = None
    no_mutable_call_in_defaults: bool | None = None
    no_shadowing_builtins: bool | None = None
    no_open_without_context_manager: bool | None = None
    # Security
    no_eval: bool | None = None
    no_exec: bool | None = None
    no_unsafe_deserialization: bool | None = None
    no_unsafe_yaml: bool | None = None
    no_shell_true: bool | None = None
    no_hardcoded_secrets: bool | None = None
    no_requests_without_timeout: bool | None = None
    # Maintainability
    max_cognitive_complexity: int | None = Field(default=None, ge=1)
    max_local_variables: int | None = Field(default=None, ge=1)
    no_debugger_statements: bool | None = None
    no_nested_imports: bool | None = None
    require_type_annotations: bool | None = None


class TaskConstraints(BaseModel):
    """Primary and secondary constraint sets with target files."""

    primary: ConstraintSet
    secondary: ConstraintSet
    target_files: list[str]
    guidance: list[str] = Field(default_factory=list)


class CLIResult(BaseModel):
    """Result from running a CLI subprocess."""

    stdout: str
    stderr: str
    exit_code: int
    parsed_json: dict | None = None


class FunctionSpec(BaseModel):
    """Function-level specification for multi-function tasks."""

    name: str
    description: str = ""
    signature: str | None = None
    examples: list[dict] = Field(default_factory=list)
    public_evals: list[dict] = Field(default_factory=list)
    hidden_evals: list[dict] = Field(default_factory=list)
    constraint_profile: str | None = None

    @model_validator(mode="after")
    def normalize_eval_fields(self) -> "FunctionSpec":
        """Apply eval alias/precedence rules and validate hidden eval schema.

        Returns:
            The validated FunctionSpec instance with normalized evals.
        """
        self.public_evals = _resolve_public_evals(
            self.examples, self.public_evals, self.model_fields_set
        )
        self.examples = list(self.public_evals)
        _validate_hidden_evals(self.hidden_evals, "FunctionSpec")
        return self


class ParsedSpec(BaseModel):
    """A parsed task specification loaded from YAML."""

    name: str
    description: str
    examples: list[dict] = Field(default_factory=list)
    public_evals: list[dict] = Field(default_factory=list)
    hidden_evals: list[dict] = Field(default_factory=list)
    signature: str | None = None
    constraint_profile: str = "default"
    target_files: list[str] = Field(default_factory=list)
    functions: list[FunctionSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_eval_fields(self) -> "ParsedSpec":
        """Apply eval alias/precedence rules and validate hidden eval schema.

        Returns:
            The validated ParsedSpec instance with normalized evals.
        """
        self.public_evals = _resolve_public_evals(
            self.examples, self.public_evals, self.model_fields_set
        )
        self.examples = list(self.public_evals)
        _validate_hidden_evals(self.hidden_evals, "ParsedSpec")
        return self


class TestCritique(BaseModel):
    """Red-team critique of generated test code."""

    __test__ = False

    exploit_vectors: list[str]
    missing_edge_cases: list[str]
    suggested_counter_tests: list[str]
    exploit_code: str | None = None
    exploit_passed: bool = False


class ConstraintResult(BaseModel):
    """Result of checking constraints against source code."""

    passed: bool
    violations: list[str]
    metrics: dict


class FunctionStatus(str, Enum):
    """Progress status for a function in an orchestrator session."""

    pending = "pending"
    tests_generated = "tests_generated"
    tests_approved = "tests_approved"
    critiqued = "critiqued"
    done = "done"


class FunctionProgress(BaseModel):
    """Tracks progress of a single function through the orchestrator loop."""

    name: str
    status: FunctionStatus = FunctionStatus.pending
    test_source: str | None = None
    critique: TestCritique | None = None


class SessionState(BaseModel):
    """Persisted state of an orchestrator session."""

    function_progress: list[FunctionProgress]
