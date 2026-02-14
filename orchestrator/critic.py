"""Red-team critic: reviews test code for exploitability."""

import json
import re
import subprocess
import tempfile
from pathlib import Path

from json_repair import repair_json

from orchestrator.cli_runner import run_cli_agent
from orchestrator.config import Config
from orchestrator.models import TestCritique
from orchestrator.prompts import build_critic_prompt, build_exploit_prompt  # noqa: F401
from orchestrator.test_generator import extract_python_from_response


def parse_critique(raw_json: str) -> TestCritique:
    """Parse a JSON string into a TestCritique model.

    Uses ``json_repair`` to handle malformed JSON from LLMs (unescaped
    braces, trailing commas, missing quotes, etc.) before parsing.

    Args:
        raw_json: JSON string from critique response.

    Returns:
        TestCritique model instance.
    """
    data = repair_json(raw_json, return_objects=True)
    if not isinstance(data, dict):
        raise ValueError("Critique response did not contain a JSON object")
    return TestCritique(**data)


def run_exploit_check(test_source: str, spec, config: Config) -> tuple[bool, str]:
    """Generate and execute a cheating implementation against tests.

    Args:
        test_source: Approved Python test source code.
        spec: Parsed function specification used to build the exploit prompt.
        config: Runtime config with critic agent/model and budget.

    Returns:
        Tuple of (passed, code), where passed is True when exploit code passes
        pytest and code is the extracted exploit implementation (or empty).
    """
    prompt = build_exploit_prompt(test_source, spec)
    result = run_cli_agent(
        prompt,
        config.critic_agent,
        config.critic_model,
        config.max_budget_usd,
    )
    if result.exit_code != 0:
        return False, ""

    try:
        exploit_code = extract_python_from_response(result.stdout).strip()
    except (SyntaxError, ValueError):
        return False, ""

    if not exploit_code:
        return False, ""

    passed = _run_exploit_pytest(test_source, exploit_code)
    return passed, exploit_code


_STDLIB_AND_TEST = frozenset({
    "pytest", "unittest", "collections", "typing", "dataclasses",
    "functools", "itertools", "math", "os", "sys", "re", "json",
    "pathlib", "abc", "enum", "copy", "operator", "random",
    "datetime", "decimal", "fractions", "statistics", "string",
    "textwrap", "io", "contextlib", "warnings", "types",
})


def _strip_local_imports(test_source: str) -> str:
    """Remove ``from <module> import ...`` lines for non-standard modules.

    Keeps imports from pytest, unittest, stdlib, and dotted packages
    (e.g. ``unittest.mock``).  Strips lines that import from local
    single-word modules like the function under test.

    Args:
        test_source: Python test source code.

    Returns:
        Source with local import lines removed.
    """
    lines = []
    for line in test_source.splitlines():
        m = re.match(r"^from\s+(\w+)\s+import\s+", line)
        if m and m.group(1) not in _STDLIB_AND_TEST:
            continue
        lines.append(line)
    return "\n".join(lines)


def _run_exploit_pytest(test_source: str, exploit_code: str) -> bool:
    """Run pytest for generated tests against exploit implementation.

    Args:
        test_source: Python test code to execute.
        exploit_code: Exploit implementation under test.

    Returns:
        True when pytest exits successfully, otherwise False.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        exploit_path = temp_path / "exploit_impl.py"
        test_path = temp_path / "test_generated.py"

        exploit_path.write_text(exploit_code, encoding="utf-8")
        cleaned = _strip_local_imports(test_source)
        test_path.write_text(
            "from exploit_impl import *\n\n" + cleaned + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            ["pytest", str(test_path), "-q"],
            cwd=temp_path,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
