"""Static analysis constraint checking using radon and AST inspection."""

import ast
import builtins

from radon.complexity import cc_visit

from orchestrator.models import ConstraintResult, ConstraintSet, TaskConstraints


def check_constraints(
    source_code: str, constraints: TaskConstraints
) -> tuple[ConstraintResult, ConstraintResult]:
    """Check source code against primary and secondary constraints.

    Args:
        source_code: Python source code to analyze.
        constraints: TaskConstraints with primary and secondary gates.

    Returns:
        Tuple of (primary_result, secondary_result).
    """
    primary = _evaluate(source_code, constraints.primary)
    if not primary.passed:
        secondary = ConstraintResult(passed=True, violations=[], metrics={})
    else:
        secondary = _evaluate(source_code, constraints.secondary)
    return primary, secondary


def _evaluate(source_code: str, cs: ConstraintSet) -> ConstraintResult:
    """Evaluate a single ConstraintSet against source code.

    Args:
        source_code: Python source code to analyze.
        cs: ConstraintSet to check against.

    Returns:
        ConstraintResult with pass/fail status and violations.
    """
    violations: list[str] = []
    metrics: dict = {}
    for checker in _CHECKERS:
        checker(source_code, cs, violations, metrics)
    return ConstraintResult(passed=len(violations) == 0, violations=violations, metrics=metrics)


def _chk_cyclomatic_complexity(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check cyclomatic complexity constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.max_cyclomatic_complexity is None:
        return
    max_cc = _max_cyclomatic_complexity(src)
    m["cyclomatic_complexity"] = max_cc
    if max_cc > cs.max_cyclomatic_complexity:
        v.append(f"Cyclomatic complexity {max_cc} > max {cs.max_cyclomatic_complexity}")


def _chk_lines_per_function(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check lines per function constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.max_lines_per_function is None:
        return
    max_lines = _max_function_lines(src)
    m["lines_per_function"] = max_lines
    if max_lines > cs.max_lines_per_function:
        v.append(f"Function has {max_lines} lines > max {cs.max_lines_per_function}")


def _chk_total_lines(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check total lines constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.max_total_lines is None:
        return
    total = len(src.splitlines())
    m["total_lines"] = total
    if total > cs.max_total_lines:
        v.append(f"Total lines {total} > max {cs.max_total_lines}")


def _chk_docstrings(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check docstring requirement.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.require_docstrings is not True:
        return
    docstring_violations = _check_docstrings(src)
    m["missing_docstrings"] = docstring_violations
    v.extend(docstring_violations)


def _chk_time_complexity(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check time complexity constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.max_time_complexity is None:
        return
    estimated = _estimate_time_complexity(src)
    m["time_complexity"] = estimated
    if _complexity_rank(estimated) > _complexity_rank(cs.max_time_complexity):
        v.append(f"Time complexity {estimated} exceeds max {cs.max_time_complexity}")


def _chk_parameters(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check max parameters constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.max_parameters is None:
        return
    max_params = _max_parameters(src)
    m["max_parameters"] = max_params
    if max_params > cs.max_parameters:
        v.append(f"Function has {max_params} parameters > max {cs.max_parameters}")


def _chk_nested_depth(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check max nesting depth constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.max_nested_depth is None:
        return
    depth = _max_nesting_depth(src)
    m["max_nested_depth"] = depth
    if depth > cs.max_nested_depth:
        v.append(f"Nesting depth {depth} > max {cs.max_nested_depth}")


def _chk_return_statements(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check max return statements constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.max_return_statements is None:
        return
    max_returns = _max_return_statements(src)
    m["max_return_statements"] = max_returns
    if max_returns > cs.max_return_statements:
        v.append(
            f"Function has {max_returns} return statements > max {cs.max_return_statements}"
        )


def _chk_print_statements(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no print statements constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_print_statements is not True:
        return
    prints = _find_print_calls(src)
    m["print_statements"] = prints
    for loc in prints:
        v.append(f"Print statement at line {loc}")


def _chk_star_imports(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no star imports constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_star_imports is not True:
        return
    stars = _find_star_imports(src)
    m["star_imports"] = stars
    for mod in stars:
        v.append(f"Star import: from {mod} import *")


def _chk_mutable_defaults(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no mutable defaults constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_mutable_defaults is not True:
        return
    mutables = _find_mutable_defaults(src)
    m["mutable_defaults"] = mutables
    for name in mutables:
        v.append(f"Mutable default argument in {name}")


def _chk_global_state(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no global state constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_global_state is not True:
        return
    globals_found = _find_global_state(src)
    m["global_state"] = globals_found
    for name in globals_found:
        v.append(f"Global mutable state: {name}")


def _chk_allowed_imports(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check allowed imports constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.allowed_imports is None:
        return
    forbidden = _check_imports(src, cs.allowed_imports)
    m["forbidden_imports"] = forbidden
    for imp in forbidden:
        v.append(f"Forbidden import: {imp}")


def _chk_bare_except(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no bare except constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_bare_except is not True:
        return
    lines = _find_bare_excepts(src)
    m["bare_excepts"] = lines
    for ln in lines:
        v.append(f"Bare except at line {ln}")


def _chk_try_except_pass(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no try-except-pass constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_try_except_pass is not True:
        return
    lines = _find_try_except_pass(src)
    m["try_except_pass"] = lines
    for ln in lines:
        v.append(f"Silenced exception (except/pass) at line {ln}")


def _chk_return_in_finally(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no return in finally constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_return_in_finally is not True:
        return
    lines = _find_return_in_finally(src)
    m["return_in_finally"] = lines
    for ln in lines:
        v.append(f"Return/break/continue in finally block at line {ln}")


def _chk_unreachable_code(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no unreachable code constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_unreachable_code is not True:
        return
    lines = _find_unreachable_code(src)
    m["unreachable_code"] = lines
    for ln in lines:
        v.append(f"Unreachable code at line {ln}")


def _chk_duplicate_dict_keys(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no duplicate dict keys constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_duplicate_dict_keys is not True:
        return
    lines = _find_duplicate_dict_keys(src)
    m["duplicate_dict_keys"] = lines
    for ln in lines:
        v.append(f"Duplicate dictionary key at line {ln}")


def _chk_loop_variable_closure(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no loop variable closure constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_loop_variable_closure is not True:
        return
    lines = _find_loop_closures(src)
    m["loop_variable_closures"] = lines
    for ln in lines:
        v.append(f"Closure captures loop variable at line {ln}")


def _chk_mutable_call_defaults(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no mutable call in defaults constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_mutable_call_in_defaults is not True:
        return
    names = _find_call_defaults(src)
    m["mutable_call_defaults"] = names
    for name in names:
        v.append(f"Function call in default argument in {name}")


def _chk_shadowing_builtins(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no shadowing builtins constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_shadowing_builtins is not True:
        return
    names = _find_shadowed_builtins(src)
    m["shadowed_builtins"] = names
    for name in names:
        v.append(f"Shadows builtin: {name}")


def _chk_open_without_with(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no open without context manager constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_open_without_context_manager is not True:
        return
    lines = _find_open_without_with(src)
    m["open_without_with"] = lines
    for ln in lines:
        v.append(f"open() without context manager at line {ln}")


def _chk_eval(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no eval constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_eval is not True:
        return
    lines = _find_calls_by_name(src, "eval")
    m["eval_calls"] = lines
    for ln in lines:
        v.append(f"eval() call at line {ln}")


def _chk_exec(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no exec constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_exec is not True:
        return
    lines = _find_calls_by_name(src, "exec")
    m["exec_calls"] = lines
    for ln in lines:
        v.append(f"exec() call at line {ln}")


def _chk_unsafe_deserialization(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no unsafe deserialization constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_unsafe_deserialization is not True:
        return
    lines = _find_unsafe_deser(src)
    m["unsafe_deserialization"] = lines
    for ln in lines:
        v.append(f"Unsafe deserialization at line {ln}")


def _chk_unsafe_yaml(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no unsafe yaml constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_unsafe_yaml is not True:
        return
    lines = _find_unsafe_yaml(src)
    m["unsafe_yaml"] = lines
    for ln in lines:
        v.append(f"Unsafe yaml.load() without SafeLoader at line {ln}")


def _chk_shell_true(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no shell=True constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_shell_true is not True:
        return
    lines = _find_shell_true(src)
    m["shell_true"] = lines
    for ln in lines:
        v.append(f"subprocess with shell=True at line {ln}")


def _chk_hardcoded_secrets(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no hardcoded secrets constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_hardcoded_secrets is not True:
        return
    names = _find_hardcoded_secrets(src)
    m["hardcoded_secrets"] = names
    for name in names:
        v.append(f"Hardcoded secret in variable: {name}")


def _chk_requests_no_timeout(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no requests without timeout constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_requests_without_timeout is not True:
        return
    lines = _find_requests_no_timeout(src)
    m["requests_no_timeout"] = lines
    for ln in lines:
        v.append(f"HTTP request without timeout at line {ln}")


def _chk_cognitive_complexity(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check cognitive complexity constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.max_cognitive_complexity is None:
        return
    max_cc = _max_cognitive_complexity(src)
    m["cognitive_complexity"] = max_cc
    if max_cc > cs.max_cognitive_complexity:
        v.append(f"Cognitive complexity {max_cc} > max {cs.max_cognitive_complexity}")


def _chk_local_variables(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check max local variables constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.max_local_variables is None:
        return
    max_locals = _max_local_variables(src)
    m["max_local_variables"] = max_locals
    if max_locals > cs.max_local_variables:
        v.append(f"Function has {max_locals} local variables > max {cs.max_local_variables}")


def _chk_debugger_statements(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no debugger statements constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_debugger_statements is not True:
        return
    lines = _find_debugger_stmts(src)
    m["debugger_statements"] = lines
    for ln in lines:
        v.append(f"Debugger statement at line {ln}")


def _chk_nested_imports(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check no nested imports constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.no_nested_imports is not True:
        return
    lines = _find_nested_imports(src)
    m["nested_imports"] = lines
    for ln in lines:
        v.append(f"Nested import at line {ln}")


def _chk_type_annotations(src: str, cs: ConstraintSet, v: list, m: dict) -> None:
    """Check require type annotations constraint.

    Args:
        src: Source code.
        cs: Constraint set.
        v: Violations list.
        m: Metrics dict.
    """
    if cs.require_type_annotations is not True:
        return
    names = _find_unannotated_fns(src)
    m["unannotated_functions"] = names
    for name in names:
        v.append(f"Missing type annotations in {name}")


_CHECKERS = [
    _chk_cyclomatic_complexity,
    _chk_lines_per_function,
    _chk_total_lines,
    _chk_docstrings,
    _chk_time_complexity,
    _chk_parameters,
    _chk_nested_depth,
    _chk_return_statements,
    _chk_print_statements,
    _chk_star_imports,
    _chk_mutable_defaults,
    _chk_global_state,
    _chk_allowed_imports,
    _chk_bare_except,
    _chk_try_except_pass,
    _chk_return_in_finally,
    _chk_unreachable_code,
    _chk_duplicate_dict_keys,
    _chk_loop_variable_closure,
    _chk_mutable_call_defaults,
    _chk_shadowing_builtins,
    _chk_open_without_with,
    _chk_eval,
    _chk_exec,
    _chk_unsafe_deserialization,
    _chk_unsafe_yaml,
    _chk_shell_true,
    _chk_hardcoded_secrets,
    _chk_requests_no_timeout,
    _chk_cognitive_complexity,
    _chk_local_variables,
    _chk_debugger_statements,
    _chk_nested_imports,
    _chk_type_annotations,
]


def _max_cyclomatic_complexity(source_code: str) -> int:
    """Return the maximum cyclomatic complexity across all functions.

    Args:
        source_code: Python source code to analyze.

    Returns:
        Maximum cyclomatic complexity value.
    """
    blocks = cc_visit(source_code)
    if not blocks:
        return 1
    return max(b.complexity for b in blocks)


def _max_function_lines(source_code: str) -> int:
    """Return the maximum number of lines in any function body.

    Args:
        source_code: Python source code to analyze.

    Returns:
        Maximum number of lines in any function.
    """
    tree = ast.parse(source_code)
    max_lines = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_lines = node.end_lineno - node.lineno + 1
            max_lines = max(max_lines, func_lines)
    return max_lines


def _check_docstrings(source_code: str) -> list[str]:
    """Return names of functions/classes with invalid or missing docstrings.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of violation messages for docstring issues.
    """
    tree = ast.parse(source_code)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            issue = _get_docstring_issue(node)
            if issue:
                violations.append(issue)
    return violations


def _get_docstring_issue(node: ast.AST) -> str | None:
    """Get the docstring issue for an AST node, if any.

    Args:
        node: AST node to check.

    Returns:
        Error message if there's a docstring issue, None otherwise.
    """
    body = getattr(node, "body", [])
    if not body:
        return f"Missing docstring: {node.name}"

    first = body[0]
    if not (
        isinstance(first, ast.Expr)
        and isinstance(first.value, (ast.Constant,))
        and isinstance(first.value.value, str)
    ):
        return f"Missing docstring: {node.name}"

    docstring = first.value.value

    # For classes, just require a docstring to exist
    if isinstance(node, ast.ClassDef):
        return None

    # For functions, check if Args: and Returns: sections are needed
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        # Check if function has parameters (excluding self/cls)
        params = [arg.arg for arg in node.args.args if arg.arg not in ("self", "cls")]
        needs_args = len(params) > 0

        # Check if function has a return statement with a value
        needs_returns = _has_return_value(node)

        # Check for Args: section if needed
        if needs_args and "Args:" not in docstring:
            return f"{node.name}: missing Args section in docstring"

        # Check for Returns: section if needed
        if needs_returns and "Returns:" not in docstring:
            return f"{node.name}: missing Returns section in docstring"

    return None


def _has_return_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function has a return statement with a value.

    Args:
        node: Function AST node to check.

    Returns:
        True if function returns a value, False otherwise.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value is not None:
            return True
    return False


def _check_imports(source_code: str, allowed: list[str]) -> list[str]:
    """Return import names not in the allowed list.

    Args:
        source_code: Python source code to analyze.
        allowed: List of allowed import names.

    Returns:
        List of forbidden import names.
    """
    tree = ast.parse(source_code)
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in allowed:
                    forbidden.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module not in allowed:
                forbidden.append(node.module)
    return forbidden


_COMPLEXITY_ORDER = {
    "O(1)": 0,
    "O(log n)": 1,
    "O(n)": 2,
    "O(n log n)": 3,
    "O(n^2)": 4,
    "O(n^3)": 5,
    "O(2^n)": 6,
}

_NESTING_TO_COMPLEXITY = {
    0: "O(1)",
    1: "O(n)",
    2: "O(n^2)",
    3: "O(n^3)",
}


def _complexity_rank(complexity: str) -> int:
    """Map a complexity string to a comparable rank.

    Args:
        complexity: Big-O notation string.

    Returns:
        Integer rank for comparison.
    """
    return _COMPLEXITY_ORDER.get(complexity, len(_COMPLEXITY_ORDER))


def _estimate_time_complexity(source_code: str) -> str:
    """Estimate time complexity from maximum loop nesting depth.

    Args:
        source_code: Python source code to analyze.

    Returns:
        Big-O notation string based on loop nesting.
    """
    tree = ast.parse(source_code)
    max_depth = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            depth = _max_loop_depth(node, 0)
            max_depth = max(max_depth, depth)
    return _NESTING_TO_COMPLEXITY.get(max_depth, f"O(n^{max_depth})")


def _max_loop_depth(node: ast.AST, current: int) -> int:
    """Recursively find the maximum loop nesting depth.

    Args:
        node: AST node to inspect.
        current: Current nesting depth.

    Returns:
        Maximum loop nesting depth found.
    """
    max_depth = current
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.For, ast.While)):
            max_depth = max(max_depth, _max_loop_depth(child, current + 1))
        else:
            max_depth = max(max_depth, _max_loop_depth(child, current))
    return max_depth


def _max_parameters(source_code: str) -> int:
    """Return the maximum parameter count across all functions.

    Args:
        source_code: Python source code to analyze.

    Returns:
        Maximum number of parameters (excluding self/cls).
    """
    tree = ast.parse(source_code)
    max_params = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
            max_params = max(max_params, len(params))
    return max_params


def _max_nesting_depth(source_code: str) -> int:
    """Return the maximum control flow nesting depth.

    Args:
        source_code: Python source code to analyze.

    Returns:
        Maximum nesting depth of if/for/while/try blocks.
    """
    tree = ast.parse(source_code)
    max_depth = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            depth = _walk_nesting(node, 0)
            max_depth = max(max_depth, depth)
    return max_depth


def _walk_nesting(node: ast.AST, current: int) -> int:
    """Recursively find the maximum control flow nesting depth.

    Args:
        node: AST node to inspect.
        current: Current nesting depth.

    Returns:
        Maximum nesting depth found.
    """
    _nesting_types = (ast.If, ast.For, ast.While, ast.Try, ast.With)
    max_depth = current
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _nesting_types):
            max_depth = max(max_depth, _walk_nesting(child, current + 1))
        else:
            max_depth = max(max_depth, _walk_nesting(child, current))
    return max_depth


def _max_return_statements(source_code: str) -> int:
    """Return the maximum number of return statements in any function.

    Args:
        source_code: Python source code to analyze.

    Returns:
        Maximum return statement count across all functions.
    """
    tree = ast.parse(source_code)
    max_returns = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            count = sum(1 for child in ast.walk(node) if isinstance(child, ast.Return))
            max_returns = max(max_returns, count)
    return max_returns


def _find_print_calls(source_code: str) -> list[int]:
    """Find line numbers of print() calls.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers where print() is called.
    """
    tree = ast.parse(source_code)
    lines = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            lines.append(node.lineno)
    return lines


def _find_star_imports(source_code: str) -> list[str]:
    """Find modules imported with wildcard.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of module names with star imports.
    """
    tree = ast.parse(source_code)
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    modules.append(node.module or "")
    return modules


def _find_mutable_defaults(source_code: str) -> list[str]:
    """Find functions with mutable default arguments.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of function names with mutable defaults.
    """
    tree = ast.parse(source_code)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + node.args.kw_defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    names.append(node.name)
                    break
    return names


def _find_global_state(source_code: str) -> list[str]:
    """Find module-level mutable variable assignments.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of variable names that represent mutable global state.
    """
    tree = ast.parse(source_code)
    names = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # Skip UPPER_CASE names (constants by convention)
                    if target.id != target.id.upper():
                        names.append(target.id)
    return names


# --- Correctness helpers ---


def _find_bare_excepts(source_code: str) -> list[int]:
    """Find line numbers of bare except clauses.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers with bare except.
    """
    tree = ast.parse(source_code)
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.ExceptHandler) and n.type is None]


def _find_try_except_pass(source_code: str) -> list[int]:
    """Find line numbers of except clauses with only pass.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers with except/pass.
    """
    tree = ast.parse(source_code)
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                lines.append(node.lineno)
    return lines


def _find_return_in_finally(source_code: str) -> list[int]:
    """Find return/break/continue statements inside finally blocks.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers of jump statements in finally.
    """
    tree = ast.parse(source_code)
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for stmt in node.finalbody:
                for child in _walk_skip_functions(stmt):
                    if isinstance(child, (ast.Return, ast.Break, ast.Continue)):
                        lines.append(child.lineno)
    return lines


def _walk_skip_functions(node: ast.AST):
    """Walk AST nodes without entering nested function definitions.

    Args:
        node: Starting AST node.

    Yields:
        AST nodes excluding nested function internals.
    """
    yield node
    for child in ast.iter_child_nodes(node):
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from _walk_skip_functions(child)


def _find_unreachable_code(source_code: str) -> list[int]:
    """Find statements after return/raise/break/continue.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers of unreachable statements.
    """
    tree = ast.parse(source_code)
    lines = []
    terminal = (ast.Return, ast.Raise, ast.Break, ast.Continue)
    for node in ast.walk(tree):
        for attr in ("body", "orelse", "finalbody"):
            stmts = getattr(node, attr, None)
            if not isinstance(stmts, list):
                continue
            for i, stmt in enumerate(stmts):
                if isinstance(stmt, terminal) and i < len(stmts) - 1:
                    lines.append(stmts[i + 1].lineno)
    return lines


def _find_duplicate_dict_keys(source_code: str) -> list[int]:
    """Find duplicate constant keys in dictionary literals.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers with duplicate keys.
    """
    tree = ast.parse(source_code)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        seen: set = set()
        for key in node.keys:
            if key is None:
                continue
            if isinstance(key, ast.Constant) and key.value in seen:
                lines.append(key.lineno)
            elif isinstance(key, ast.Constant):
                seen.add(key.value)
    return lines


def _find_loop_closures(source_code: str) -> list[int]:
    """Find closures inside for-loops that capture the loop variable.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers of unsafe closures.
    """
    tree = ast.parse(source_code)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        loop_vars = _extract_target_names(node.target)
        for child in ast.walk(node):
            if child is node:
                continue
            if not isinstance(child, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _closure_uses_loop_var(child, loop_vars):
                lines.append(child.lineno)
    return lines


def _extract_target_names(target: ast.AST) -> set[str]:
    """Extract variable names from an assignment target.

    Args:
        target: AST assignment target node.

    Returns:
        Set of variable name strings.
    """
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for elt in target.elts:
            names.update(_extract_target_names(elt))
        return names
    return set()


def _closure_uses_loop_var(node: ast.AST, loop_vars: set[str]) -> bool:
    """Check if a closure references loop variables without capturing them.

    Args:
        node: Lambda or function definition node.
        loop_vars: Set of loop variable names to check.

    Returns:
        True if the closure unsafely references a loop variable.
    """
    defaults = _get_default_names(node)
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in loop_vars:
            if child.id not in defaults:
                return True
    return False


def _get_default_names(node: ast.AST) -> set[str]:
    """Get parameter names that have default values.

    Args:
        node: Lambda or function definition node.

    Returns:
        Set of parameter names with defaults.
    """
    args = getattr(node, "args", None)
    if args is None:
        return set()
    names: set[str] = set()
    n_defaults = len(args.defaults)
    n_args = len(args.args)
    for i in range(n_defaults):
        names.add(args.args[n_args - n_defaults + i].arg)
    return names


_SAFE_CALL_DEFAULTS = frozenset({
    "frozenset", "tuple", "bytes", "int", "float", "str", "bool", "complex",
    "Field", "field", "dataclass", "property",
})


def _find_call_defaults(source_code: str) -> list[str]:
    """Find functions with function calls in default arguments.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of function names with call defaults.
    """
    tree = ast.parse(source_code)
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for default in node.args.defaults + node.args.kw_defaults:
            if default is None:
                continue
            if isinstance(default, ast.Call) and _get_call_name(default) not in _SAFE_CALL_DEFAULTS:
                names.append(node.name)
                break
    return names


def _get_call_name(node: ast.Call) -> str:
    """Extract the function name from a Call node.

    Args:
        node: AST Call node.

    Returns:
        Function name string, or empty string if unresolvable.
    """
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


_BUILTIN_NAMES = frozenset(dir(builtins)) - frozenset({
    "__name__", "__doc__", "__package__", "__loader__", "__spec__",
    "__builtins__", "__file__", "__cached__", "None", "True", "False",
    "__build_class__", "__import__",
})


def _find_shadowed_builtins(source_code: str) -> list[str]:
    """Find variable/function names that shadow Python builtins.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of shadowed builtin names.
    """
    tree = ast.parse(source_code)
    shadows: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in _BUILTIN_NAMES and node.name not in seen:
                shadows.append(node.name)
                seen.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in _BUILTIN_NAMES:
                    if target.id not in seen:
                        shadows.append(target.id)
                        seen.add(target.id)
    return shadows


def _find_open_without_with(source_code: str) -> list[int]:
    """Find open() calls not used as context managers.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers of bare open() calls.
    """
    tree = ast.parse(source_code)
    with_opens: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                if _is_open_call(item.context_expr):
                    with_opens.add(id(item.context_expr))
    lines = []
    for node in ast.walk(tree):
        if _is_open_call(node) and id(node) not in with_opens:
            lines.append(node.lineno)
    return lines


def _is_open_call(node: ast.AST) -> bool:
    """Check if an AST node is a call to open().

    Args:
        node: AST node to check.

    Returns:
        True if the node is an open() call.
    """
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open")


# --- Security helpers ---


def _find_calls_by_name(source_code: str, name: str) -> list[int]:
    """Find line numbers of calls to a specific function name.

    Args:
        source_code: Python source code to analyze.
        name: Function name to search for.

    Returns:
        List of line numbers where the function is called.
    """
    tree = ast.parse(source_code)
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == name]


_UNSAFE_DESER_ATTRS = frozenset({"load", "loads", "Unpickler"})
_UNSAFE_DESER_MODULES = frozenset({"pickle", "marshal"})


def _find_unsafe_deser(source_code: str) -> list[int]:
    """Find unsafe deserialization calls (pickle/marshal).

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers with unsafe deserialization.
    """
    tree = ast.parse(source_code)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if (isinstance(node.func, ast.Attribute)
                and node.func.attr in _UNSAFE_DESER_ATTRS
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in _UNSAFE_DESER_MODULES):
            lines.append(node.lineno)
    return lines


def _find_unsafe_yaml(source_code: str) -> list[int]:
    """Find yaml.load() calls without SafeLoader.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers with unsafe yaml.load().
    """
    tree = ast.parse(source_code)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute)
                and node.func.attr == "load"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "yaml"):
            continue
        has_loader = any(kw.arg == "Loader" for kw in node.keywords)
        if not has_loader:
            lines.append(node.lineno)
    return lines


def _find_shell_true(source_code: str) -> list[int]:
    """Find subprocess calls with shell=True.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers with shell=True.
    """
    tree = ast.parse(source_code)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if (kw.arg == "shell"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True):
                lines.append(node.lineno)
                break
    return lines


_SECRET_PATTERNS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "access_key", "secret_key", "private_key",
})


def _find_hardcoded_secrets(source_code: str) -> list[str]:
    """Find variables with secret-like names assigned string literals.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of variable names containing hardcoded secrets.
    """
    tree = ast.parse(source_code)
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if (target.id.lower() in _SECRET_PATTERNS
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)):
                names.append(target.id)
    return names


_REQUEST_METHODS = frozenset({"get", "post", "put", "delete", "patch", "head", "options"})


def _find_requests_no_timeout(source_code: str) -> list[int]:
    """Find HTTP request calls without a timeout parameter.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers of requests without timeout.
    """
    tree = ast.parse(source_code)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute)
                and node.func.attr in _REQUEST_METHODS
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "requests"):
            continue
        has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
        if not has_timeout:
            lines.append(node.lineno)
    return lines


# --- Maintainability helpers ---


def _max_cognitive_complexity(source_code: str) -> int:
    """Return the maximum cognitive complexity across all functions.

    Args:
        source_code: Python source code to analyze.

    Returns:
        Maximum cognitive complexity value.
    """
    tree = ast.parse(source_code)
    max_cc = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cc = _cognitive_for_node(node, 0)
            max_cc = max(max_cc, cc)
    return max_cc


def _cognitive_for_node(node: ast.AST, nesting: int) -> int:
    """Compute cognitive complexity for an AST subtree.

    Args:
        node: AST node to analyze.
        nesting: Current nesting depth.

    Returns:
        Cognitive complexity score.
    """
    total = 0
    for child in ast.iter_child_nodes(node):
        total += _cognitive_score(child, nesting)
    return total


def _cognitive_score(child: ast.AST, nesting: int) -> int:
    """Score a single AST node for cognitive complexity.

    Args:
        child: AST node to score.
        nesting: Current nesting depth.

    Returns:
        Cognitive complexity contribution of this node.
    """
    if isinstance(child, ast.If):
        return _cognitive_for_if(child, nesting)
    if isinstance(child, (ast.For, ast.While)):
        score = 1 + nesting
        return score + _cognitive_for_node(child, nesting + 1)
    if isinstance(child, ast.BoolOp):
        return 1 + _cognitive_for_node(child, nesting)
    if isinstance(child, ast.IfExp):
        return 1 + nesting + _cognitive_for_node(child, nesting)
    if isinstance(child, ast.Try):
        return _cognitive_for_try(child, nesting)
    if isinstance(child, (ast.Break, ast.Continue)):
        return 1
    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return _cognitive_for_node(child, nesting + 1)
    return _cognitive_for_node(child, nesting)


def _cognitive_for_if(node: ast.If, nesting: int) -> int:
    """Compute cognitive complexity for an if/elif/else chain.

    Args:
        node: If AST node.
        nesting: Current nesting depth.

    Returns:
        Cognitive complexity for the entire if chain.
    """
    score = 1 + nesting
    score += _cognitive_for_node_stmts(node.body, nesting + 1)
    orelse = node.orelse
    if orelse:
        if len(orelse) == 1 and isinstance(orelse[0], ast.If):
            score += 1 + _cognitive_for_if_body(orelse[0], nesting)
        else:
            score += 1 + _cognitive_for_node_stmts(orelse, nesting + 1)
    return score


def _cognitive_for_if_body(node: ast.If, nesting: int) -> int:
    """Compute cognitive complexity for an elif branch.

    Args:
        node: If AST node representing an elif.
        nesting: Current nesting depth.

    Returns:
        Cognitive complexity for elif and its continuations.
    """
    score = _cognitive_for_node_stmts(node.body, nesting + 1)
    orelse = node.orelse
    if orelse:
        if len(orelse) == 1 and isinstance(orelse[0], ast.If):
            score += 1 + _cognitive_for_if_body(orelse[0], nesting)
        else:
            score += 1 + _cognitive_for_node_stmts(orelse, nesting + 1)
    return score


def _cognitive_for_try(node: ast.Try, nesting: int) -> int:
    """Compute cognitive complexity for a try/except block.

    Args:
        node: Try AST node.
        nesting: Current nesting depth.

    Returns:
        Cognitive complexity for the try block.
    """
    score = _cognitive_for_node_stmts(node.body, nesting)
    for handler in node.handlers:
        score += 1 + nesting + _cognitive_for_node_stmts(handler.body, nesting + 1)
    score += _cognitive_for_node_stmts(node.orelse, nesting)
    score += _cognitive_for_node_stmts(node.finalbody, nesting)
    return score


def _cognitive_for_node_stmts(stmts: list, nesting: int) -> int:
    """Compute cognitive complexity for a list of statements.

    Args:
        stmts: List of AST statement nodes.
        nesting: Current nesting depth.

    Returns:
        Total cognitive complexity for the statements.
    """
    total = 0
    for stmt in stmts:
        total += _cognitive_score(stmt, nesting)
    return total


def _max_local_variables(source_code: str) -> int:
    """Return the max local variable count across all functions.

    Args:
        source_code: Python source code to analyze.

    Returns:
        Maximum number of local variables in any function.
    """
    tree = ast.parse(source_code)
    max_locals = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = _get_param_names(node)
        locals_set: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                if child.id not in params:
                    locals_set.add(child.id)
        max_locals = max(max_locals, len(locals_set))
    return max_locals


def _get_param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Get all parameter names for a function.

    Args:
        node: Function definition node.

    Returns:
        Set of parameter name strings.
    """
    names = {a.arg for a in node.args.args}
    names.update(a.arg for a in node.args.kwonlyargs)
    if node.args.vararg:
        names.add(node.args.vararg.arg)
    if node.args.kwarg:
        names.add(node.args.kwarg.arg)
    return names


def _find_debugger_stmts(source_code: str) -> list[int]:
    """Find debugger imports and breakpoint() calls.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers with debugger statements.
    """
    tree = ast.parse(source_code)
    debuggers = {"pdb", "ipdb", "pudb"}
    lines = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "breakpoint"):
            lines.append(node.lineno)
        elif isinstance(node, ast.Import):
            if any(a.name in debuggers for a in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module in debuggers:
            lines.append(node.lineno)
    return lines


def _find_nested_imports(source_code: str) -> list[int]:
    """Find import statements inside functions.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of line numbers of nested imports.
    """
    tree = ast.parse(source_code)
    lines = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(func):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                lines.append(child.lineno)
    return lines


def _find_unannotated_fns(source_code: str) -> list[str]:
    """Find functions missing type annotations.

    Args:
        source_code: Python source code to analyze.

    Returns:
        List of function names without complete annotations.
    """
    tree = ast.parse(source_code)
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.returns is None:
            names.append(node.name)
            continue
        for arg in node.args.args:
            if arg.arg in ("self", "cls"):
                continue
            if arg.annotation is None:
                names.append(node.name)
                break
    return names
