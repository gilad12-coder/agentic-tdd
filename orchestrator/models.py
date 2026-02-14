"""Pydantic v2 models for the orchestrator system."""

from enum import Enum

from pydantic import BaseModel, Field


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
    constraint_profile: str | None = None


class ParsedSpec(BaseModel):
    """A parsed task specification loaded from YAML."""

    name: str
    description: str
    examples: list[dict] = Field(default_factory=list)
    signature: str | None = None
    constraint_profile: str = "default"
    target_files: list[str] = Field(default_factory=list)
    functions: list[FunctionSpec] = Field(default_factory=list)


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
