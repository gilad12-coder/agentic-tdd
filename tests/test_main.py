"""Tests for the orchestrator CLI entry point."""

from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.__main__ import build_parser, main


# --- build_parser ---


class TestBuildParser:
    """Tests for build_parser."""

    def test_build_parser_run_subcommand(self):
        """Test that build_parser parses the run subcommand."""
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml"])
        assert args.command == "run"
        assert args.spec_path == "spec.yaml"

    def test_build_parser_status_subcommand(self):
        """Test that build_parser parses the status subcommand."""
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_build_parser_run_default_profiles(self):
        """Test that build_parser uses the default profiles path."""
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml"])
        assert args.profiles == "constraints/profiles.yaml"

    def test_build_parser_run_default_session(self):
        """Test that build_parser uses the default session path for run."""
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml"])
        assert args.session == ".session.json"

    def test_build_parser_status_default_session(self):
        """Test that build_parser uses the default session path for status."""
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.session == ".session.json"

    def test_build_parser_run_auto_flag(self):
        """Test that build_parser parses the -y/--auto flag."""
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml", "-y"])
        assert args.auto is True

    def test_build_parser_run_auto_tests_flag(self):
        """Test that build_parser parses the --auto-tests flag."""
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml", "--auto-tests"])
        assert args.auto_tests is True

    def test_build_parser_run_auto_critique_flag(self):
        """Test that build_parser parses the --auto-critique flag."""
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml", "--auto-critique"])
        assert args.auto_critique is True

    def test_build_parser_run_auto_defaults_false(self):
        """Test that auto flags default to False."""
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml"])
        assert args.auto is False
        assert args.auto_tests is False
        assert args.auto_critique is False

    def test_build_parser_run_implement_flag(self):
        """Test that build_parser parses the --implement flag."""
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml", "--implement"])
        assert args.implement is True

    def test_build_parser_run_implement_default_false(self):
        """Test that --implement defaults to False."""
        parser = build_parser()
        args = parser.parse_args(["run", "spec.yaml"])
        assert args.implement is False

    def test_build_parser_implement_subcommand(self):
        """Test that build_parser parses the implement subcommand."""
        parser = build_parser()
        args = parser.parse_args(["implement", "--spec", "spec.yaml"])
        assert args.command == "implement"
        assert args.spec == "spec.yaml"

    def test_build_parser_implement_defaults(self):
        """Test that implement subcommand has correct defaults."""
        parser = build_parser()
        args = parser.parse_args(["implement", "--spec", "spec.yaml"])
        assert args.session == ".session.json"
        assert args.profiles == "constraints/profiles.yaml"
        assert args.no_docker is False


# --- main ---


class TestMain:
    """Tests for main entry point."""
    @patch("orchestrator.__main__.run_session")
    def test_main_run_calls_run_session(self, mock_run, tmp_path):
        """Test that main run subcommand calls run_session.

        Args:
            mock_run: Mocked run_session.
            tmp_path: Pytest tmp_path fixture.
        """
        spec = tmp_path / "spec.yaml"
        spec.write_text("name: test")
        main(["run", str(spec), "--profiles", "p.yaml", "--session", "s.json"])
        mock_run.assert_called_once_with(
            spec_path=spec,
            profiles_path=Path("p.yaml"),
            session_path=Path("s.json"),
            auto_tests=False,
            auto_critique=False,
            auto_implement=False,
        )

    @patch("orchestrator.__main__.run_session")
    def test_main_run_with_auto_flag(self, mock_run, tmp_path):
        """Test that -y flag sets both auto_tests and auto_critique to True.

        Args:
            mock_run: Mocked run_session.
            tmp_path: Pytest tmp_path fixture.
        """
        spec = tmp_path / "spec.yaml"
        spec.write_text("name: test")
        main(["run", str(spec), "-y"])
        mock_run.assert_called_once_with(
            spec_path=spec,
            profiles_path=Path("constraints/profiles.yaml"),
            session_path=Path(".session.json"),
            auto_tests=True,
            auto_critique=True,
            auto_implement=False,
        )

    @patch("orchestrator.__main__.run_session")
    def test_main_run_with_auto_tests_only(self, mock_run, tmp_path):
        """Test that --auto-tests sets only auto_tests to True.

        Args:
            mock_run: Mocked run_session.
            tmp_path: Pytest tmp_path fixture.
        """
        spec = tmp_path / "spec.yaml"
        spec.write_text("name: test")
        main(["run", str(spec), "--auto-tests"])
        mock_run.assert_called_once_with(
            spec_path=spec,
            profiles_path=Path("constraints/profiles.yaml"),
            session_path=Path(".session.json"),
            auto_tests=True,
            auto_critique=False,
            auto_implement=False,
        )

    @patch("orchestrator.__main__.run_session")
    def test_main_run_with_auto_critique_only(self, mock_run, tmp_path):
        """Test that --auto-critique sets only auto_critique to True.

        Args:
            mock_run: Mocked run_session.
            tmp_path: Pytest tmp_path fixture.
        """
        spec = tmp_path / "spec.yaml"
        spec.write_text("name: test")
        main(["run", str(spec), "--auto-critique"])
        mock_run.assert_called_once_with(
            spec_path=spec,
            profiles_path=Path("constraints/profiles.yaml"),
            session_path=Path(".session.json"),
            auto_tests=False,
            auto_critique=True,
            auto_implement=False,
        )

    @patch("orchestrator.__main__.show_status")
    def test_main_status_calls_show_status(self, mock_status):
        """Test that main status subcommand calls show_status.

        Args:
            mock_status: Mocked show_status.
        """
        main(["status", "--session", "s.json"])
        mock_status.assert_called_once_with(Path("s.json"))

    def test_main_no_command_exits(self):
        """Test that main exits when no subcommand is provided."""
        with pytest.raises(SystemExit):
            main([])

    @patch("orchestrator.__main__.run_session")
    def test_main_run_missing_spec_exits(self, mock_run, tmp_path):
        """Test that main exits when spec file does not exist.

        Args:
            mock_run: Mocked run_session.
            tmp_path: Pytest tmp_path fixture.
        """
        nonexistent = str(tmp_path / "nonexistent.yaml")
        with pytest.raises(SystemExit):
            main(["run", nonexistent])
        mock_run.assert_not_called()

    @patch("orchestrator.__main__.run_session")
    def test_main_run_with_implement_flag(self, mock_run, tmp_path):
        """Test that --implement passes auto_implement=True to run_session.

        Args:
            mock_run: Mocked run_session.
            tmp_path: Pytest tmp_path fixture.
        """
        spec = tmp_path / "spec.yaml"
        spec.write_text("name: test")
        main(["run", str(spec), "--implement"])
        mock_run.assert_called_once_with(
            spec_path=spec,
            profiles_path=Path("constraints/profiles.yaml"),
            session_path=Path(".session.json"),
            auto_tests=False,
            auto_critique=False,
            auto_implement=True,
        )

    @patch("orchestrator.__main__.run_implement")
    def test_main_implement_calls_run_implement(self, mock_impl, tmp_path):
        """Test that implement subcommand calls run_implement.

        Args:
            mock_impl: Mocked run_implement.
            tmp_path: Pytest tmp_path fixture.
        """
        main(["implement", "--spec", "spec.yaml", "--session", "s.json"])
        mock_impl.assert_called_once_with(
            spec_path=Path("spec.yaml"),
            profiles_path=Path("constraints/profiles.yaml"),
            session_path=Path("s.json"),
            use_docker=True,
        )

    @patch("orchestrator.__main__.run_implement")
    def test_main_implement_no_docker(self, mock_impl, tmp_path):
        """Test that --no-docker flag sets use_docker=False.

        Args:
            mock_impl: Mocked run_implement.
            tmp_path: Pytest tmp_path fixture.
        """
        main(["implement", "--spec", "s.yaml", "--no-docker"])
        mock_impl.assert_called_once_with(
            spec_path=Path("s.yaml"),
            profiles_path=Path("constraints/profiles.yaml"),
            session_path=Path(".session.json"),
            use_docker=False,
        )

    @patch("orchestrator.__main__.load_session", return_value=None)
    @patch("orchestrator.__main__.display_error")
    def test_main_status_missing_session_exits(self, mock_error, mock_load):
        """Test that main exits when session file is missing.

        Args:
            mock_error: Mocked display_error.
            mock_load: Mocked load_session.
        """
        with pytest.raises(SystemExit):
            main(["status"])
