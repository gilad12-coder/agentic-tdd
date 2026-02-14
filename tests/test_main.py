"""Tests for the orchestrator CLI entry point."""

from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.__main__ import build_parser, main


# --- build_parser ---


class TestBuildParser:
    def test_build_parser_run_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml"])
        assert args.command == "run"
        assert args.spec_path == "spec.yaml"

    def test_build_parser_status_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_build_parser_run_default_profiles(self):
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml"])
        assert args.profiles == "constraints/profiles.yaml"

    def test_build_parser_run_default_session(self):
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml"])
        assert args.session == ".session.json"

    def test_build_parser_status_default_session(self):
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.session == ".session.json"


# --- main ---


class TestMain:
    @patch("orchestrator.__main__.run_session")
    def test_main_run_calls_run_session(self, mock_run, tmp_path):
        spec = tmp_path / "spec.yaml"
        spec.write_text("name: test")
        main(["run", str(spec), "--profiles", "p.yaml", "--session", "s.json"])
        mock_run.assert_called_once_with(
            spec_path=spec,
            profiles_path=Path("p.yaml"),
            session_path=Path("s.json"),
        )

    @patch("orchestrator.__main__.show_status")
    def test_main_status_calls_show_status(self, mock_status):
        main(["status", "--session", "s.json"])
        mock_status.assert_called_once_with(Path("s.json"))

    def test_main_no_command_exits(self):
        with pytest.raises(SystemExit):
            main([])

    @patch("orchestrator.__main__.run_session")
    def test_main_run_missing_spec_exits(self, mock_run, tmp_path):
        nonexistent = str(tmp_path / "nonexistent.yaml")
        with pytest.raises(SystemExit):
            main(["run", nonexistent])
        mock_run.assert_not_called()

    @patch("orchestrator.__main__.load_session", return_value=None)
    @patch("orchestrator.__main__.display_error")
    def test_main_status_missing_session_exits(self, mock_error, mock_load):
        with pytest.raises(SystemExit):
            main(["status"])
