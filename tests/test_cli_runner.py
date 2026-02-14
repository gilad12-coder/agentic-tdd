import json
import os
import shutil
from unittest.mock import patch

import pytest

from orchestrator.cli_runner import (
    build_command,
    build_implementation_command,
    parse_cli_output,
    run_cli_agent,
)
from orchestrator.models import CLIResult


# --- Unit tests: command construction ---


class TestBuildCommand:
    def test_build_command_claude_agent(self):
        cmd = build_command(
            prompt="Write hello world",
            agent="claude",
            model="sonnet",
            budget=5.0,
        )
        assert isinstance(cmd, list)
        assert "claude" in cmd[0]
        assert "-p" in cmd
        assert "--output-format" in cmd
        prompt_idx = cmd.index("-p") + 1
        assert "Write hello world" in cmd[prompt_idx]

    def test_build_command_codex_agent(self):
        cmd = build_command(
            prompt="Write hello world",
            agent="codex",
            model="gpt-5.2-codex",
            budget=5.0,
        )
        assert "codex" in cmd[0]
        assert "--model" in cmd

    def test_build_command_includes_budget(self):
        cmd = build_command(prompt="test", agent="claude", model="sonnet", budget=3.50)
        cmd_str = " ".join(cmd)
        assert "3.5" in cmd_str

    def test_build_command_includes_model(self):
        cmd = build_command(prompt="test", agent="claude", model="haiku", budget=5.0)
        cmd_str = " ".join(cmd)
        assert "haiku" in cmd_str

    def test_build_command_includes_tool_restrictions(self):
        cmd = build_command(prompt="test", agent="claude", model="sonnet", budget=5.0)
        cmd_str = " ".join(cmd)
        assert "allowedTools" in cmd_str or "disallowedTools" in cmd_str


class TestBuildImplementationCommand:
    def test_build_implementation_command_codex(self):
        cmd = build_implementation_command(
            prompt="Make all tests pass",
            agent="codex",
            model="o4-mini",
        )
        assert "codex" in cmd[0]
        assert "exec" in cmd
        assert "--full-auto" in cmd
        assert "Make all tests pass" in cmd

    def test_build_implementation_command_claude(self):
        cmd = build_implementation_command(
            prompt="Make all tests pass",
            agent="claude",
            model="sonnet",
        )
        assert "claude" in cmd[0]
        assert "-p" in cmd
        assert "Make all tests pass" in cmd


# --- Unit tests: output parsing ---


class TestParseCliOutput:
    def test_parse_cli_output_json(self):
        stdout = json.dumps({"result": "success", "tests": ["test_1", "test_2"]})
        result = parse_cli_output(stdout=stdout, stderr="", exit_code=0)
        assert isinstance(result, CLIResult)
        assert result.parsed_json is not None
        assert result.parsed_json["result"] == "success"

    def test_parse_cli_output_non_json(self):
        result = parse_cli_output(
            stdout="Just plain text output", stderr="", exit_code=0
        )
        assert result.parsed_json is None
        assert result.stdout == "Just plain text output"

    def test_parse_cli_output_preserves_exit_code(self):
        success = parse_cli_output(stdout="ok", stderr="", exit_code=0)
        assert success.exit_code == 0

        failure = parse_cli_output(stdout="", stderr="error", exit_code=1)
        assert failure.exit_code == 1

    def test_parse_cli_output_json_with_surrounding_text(self):
        # CLI might output text before/after JSON
        stdout = 'Some preamble\n{"result": "ok"}\nSome epilogue'
        result = parse_cli_output(stdout=stdout, stderr="", exit_code=0)
        # Should still try to extract JSON
        assert result.stdout == stdout


# --- Error handling ---


class TestRunCliAgentErrorHandling:
    @patch("orchestrator.cli_runner.subprocess.run")
    def test_run_cli_agent_timeout_returns_error_result(self, mock_run):
        import subprocess as sp

        mock_run.side_effect = sp.TimeoutExpired(cmd=["claude"], timeout=300)
        result = run_cli_agent(
            prompt="test", agent="claude", model="sonnet", budget=1.0
        )
        assert result.exit_code == -1
        assert "timeout" in result.stderr.lower()

    @patch("orchestrator.cli_runner.subprocess.run")
    def test_run_cli_agent_missing_binary_returns_error_result(self, mock_run):
        mock_run.side_effect = FileNotFoundError("No such file")
        result = run_cli_agent(
            prompt="test", agent="claude", model="sonnet", budget=1.0
        )
        assert result.exit_code == -1
        assert "not found" in result.stderr.lower()


# --- Smoke tests: verify CLIs are callable ---


class TestCliSmoke:
    @pytest.mark.skipif(
        shutil.which("claude") is None or os.environ.get("CLAUDECODE") is not None,
        reason="requires claude CLI outside of a nested session",
    )
    def test_claude_returns_output(self):
        result = run_cli_agent(
            prompt="Respond with exactly: hello",
            agent="claude",
            model="sonnet",
            budget=1.0,
        )
        assert isinstance(result, CLIResult)
        assert result.exit_code == 0
        assert len(result.stdout) > 0

    @pytest.mark.skipif(
        shutil.which("codex") is None or not os.isatty(0),
        reason="requires codex CLI with interactive terminal",
    )
    def test_codex_returns_output(self):
        result = run_cli_agent(
            prompt="Respond with exactly: hello",
            agent="codex",
            model="gpt-5.2-codex",
            budget=1.0,
        )
        assert isinstance(result, CLIResult)
        assert result.exit_code == 0
        assert len(result.stdout) > 0
