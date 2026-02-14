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
    def test_function_status_has_all_states(self):
        expected = {"pending", "tests_generated", "tests_approved", "critiqued", "done"}
        actual = {s.value for s in FunctionStatus}
        assert actual == expected


# --- FunctionProgress ---


class TestFunctionProgress:
    def test_function_progress_defaults_to_pending(self):
        fp = FunctionProgress(name="login")
        assert fp.status == FunctionStatus.pending
        assert fp.test_source is None
        assert fp.critique is None


# --- create_session ---


class TestCreateSession:
    def test_create_session_maps_spec_functions(self):
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
    def test_save_session_writes_json(self, tmp_path):
        state = SessionState(function_progress=[FunctionProgress(name="add")])
        path = tmp_path / "session.json"
        save_session(state, path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert "function_progress" in data

    def test_load_session_round_trip(self, tmp_path):
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
        path = tmp_path / "nonexistent.json"
        result = load_session(path)
        assert result is None
