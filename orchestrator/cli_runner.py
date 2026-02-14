"""Subprocess wrapper for running Claude Code and Codex CLIs."""

import json
import subprocess

from orchestrator.models import CLIResult


def build_command(prompt: str, agent: str, model: str, budget: float) -> list[str]:
    """Construct a CLI command as a list of strings.

    Args:
        prompt: Prompt text for the agent.
        agent: Agent name (claude or codex).
        model: Model name to use.
        budget: Budget or max turns value.

    Returns:
        List of command arguments.
    """
    if agent == "claude":
        return [
            "claude",
            "-p", prompt,
            "--output-format", "json",
            "--model", model,
            "--max-budget-usd", str(budget),
            "--allowedTools", "",
        ]
    elif agent == "codex":
        return [
            "codex",
            "exec",
            "--model", model,
            prompt,
        ]
    else:
        raise ValueError(f"Unknown agent: {agent}")


def build_implementation_command(prompt: str, agent: str, model: str) -> list[str]:
    """Build a CLI command for implementation-phase code changes.

    Args:
        prompt: Prompt text for the implementation agent.
        agent: Agent name (claude or codex).
        model: Model name to use.

    Returns:
        List of command arguments.
    """
    if agent == "codex":
        return ["codex", "exec", "--full-auto", "-m", model, prompt]
    if agent == "claude":
        return [
            "claude",
            "-p",
            prompt,
            "--model",
            model,
            "--allowedTools",
            "Edit,Write,Read,Bash",
        ]
    raise ValueError(f"Unknown agent: {agent}")


def parse_cli_output(stdout: str, stderr: str, exit_code: int) -> CLIResult:
    """Parse raw subprocess output into a CLIResult.

    Args:
        stdout: Standard output from subprocess.
        stderr: Standard error from subprocess.
        exit_code: Process exit code.

    Returns:
        CLIResult with parsed output. When the output is Claude JSON format,
        the result text is extracted into stdout for downstream processing.
    """
    parsed_json = None
    try:
        parsed_json = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        pass

    effective_stdout = stdout
    if parsed_json and isinstance(parsed_json, dict) and "result" in parsed_json:
        effective_stdout = parsed_json["result"]

    return CLIResult(
        stdout=effective_stdout,
        stderr=stderr,
        exit_code=exit_code,
        parsed_json=parsed_json,
    )


def run_cli_agent(
    prompt: str, agent: str, model: str, budget: float, timeout: int = 300
) -> CLIResult:
    """Run a CLI agent subprocess and return the result.

    Args:
        prompt: Prompt text for the agent.
        agent: Agent name (claude or codex).
        model: Model name to use.
        budget: Budget or max turns value.
        timeout: Subprocess timeout in seconds.

    Returns:
        CLIResult with command output.
    """
    cmd = build_command(prompt, agent, model, budget)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return CLIResult(
            stdout="",
            stderr=f"Agent timeout after {timeout}s",
            exit_code=-1,
        )
    except FileNotFoundError:
        return CLIResult(
            stdout="",
            stderr=f"Agent binary not found: {cmd[0]}",
            exit_code=-1,
        )
    return parse_cli_output(result.stdout, result.stderr, result.returncode)
