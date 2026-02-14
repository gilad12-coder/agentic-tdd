"""Tests for session state management."""

import json

from orchestrator.models import (
    FunctionProgress,
    FunctionSpec,
    FunctionStatus,
    ParsedSpec,
    SessionState,
    TestCritique,
)
from orchestrator.session import create_session, load_session, save_session


# --- FunctionStatus ---


class TestFunctionStatus:
    """Tests for FunctionStatus enum."""

    def test_function_status_has_all_states(self):
        """Test that FunctionStatus has all expected state values."""
        expected = {"pending", "tests_generated", "tests_approved", "critiqued", "done"}
        actual = {s.value for s in FunctionStatus}
        assert actual == expected


# --- FunctionProgress ---


class TestFunctionProgress:
    """Tests for FunctionProgress."""

    def test_function_progress_defaults_to_pending(self):
        """Test that FunctionProgress defaults to pending status."""
        fp = FunctionProgress(name="login")
        assert fp.status == FunctionStatus.pending
        assert fp.test_source is None
        assert fp.critique is None


# --- create_session ---


class TestCreateSession:
    """Tests for create_session."""

    def test_create_session_maps_spec_functions(self):
        """Test that create_session creates progress entries for each function."""
        spec = ParsedSpec(
            name="auth",
            description="Auth module",
            examples=[],
            functions=[
                FunctionSpec(name="login", description="Log in"),
                FunctionSpec(name="logout", description="Log out"),
            ],
        )
        state = create_session(spec)
        assert len(state.function_progress) == 2
        assert state.function_progress[0].name == "login"
        assert state.function_progress[1].name == "logout"
        assert all(
            fp.status == FunctionStatus.pending for fp in state.function_progress
        )

    def test_create_session_single_function_uses_spec_name(self):
        """Test that create_session uses spec name for single-function specs."""
        spec = ParsedSpec(
            name="add",
            description="Add two numbers",
            examples=[],
        )
        state = create_session(spec)
        assert len(state.function_progress) == 1
        assert state.function_progress[0].name == "add"


# --- save_session / load_session ---


class TestSessionPersistence:
    """Tests for save_session and load_session."""

    def test_save_session_writes_json(self, tmp_path):
        """Test that save_session writes valid JSON to disk.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        state = SessionState(function_progress=[FunctionProgress(name="add")])
        path = tmp_path / "session.json"
        save_session(state, path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert "function_progress" in data

    def test_load_session_round_trip(self, tmp_path):
        """Test that save then load preserves session state.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        state = SessionState(
            function_progress=[
                FunctionProgress(
                    name="add",
                    status=FunctionStatus.critiqued,
                    test_source="def test_add(): assert add(1, 2) == 3",
                    critique=TestCritique(
                        exploit_vectors=["hardcode"],
                        missing_edge_cases=["negative"],
                        suggested_counter_tests=["test_neg"],
                    ),
                ),
            ]
        )
        path = tmp_path / "session.json"
        save_session(state, path)
        loaded = load_session(path)
        assert loaded is not None
        assert loaded.function_progress[0].name == "add"
        assert loaded.function_progress[0].status == FunctionStatus.critiqued
        assert loaded.function_progress[0].test_source is not None
        assert loaded.function_progress[0].critique is not None
        assert loaded.function_progress[0].critique.exploit_vectors == ["hardcode"]

    def test_load_session_missing_file_returns_none(self, tmp_path):
        """Test that load_session returns None for missing files.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        path = tmp_path / "nonexistent.json"
        result = load_session(path)
        assert result is None
