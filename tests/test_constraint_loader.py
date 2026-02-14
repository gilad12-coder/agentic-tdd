import pytest
import yaml

from orchestrator.constraint_loader import load_profiles, resolve_constraints
from orchestrator.models import (
    ConstraintSet,
    FunctionSpec,
    ParsedSpec,
    TaskConstraints,
)
from orchestrator.spec_intake import parse_spec


PROFILES_DATA = {
    "profiles": {
        "default": {
            "primary": {"max_cyclomatic_complexity": 10},
            "secondary": {"require_docstrings": True},
            "guidance": [
                "Prefer early returns over nested if/else.",
                "Avoid inline comments unless ambiguous.",
            ],
        },
        "strict": {
            "primary": {
                "max_cyclomatic_complexity": 5,
                "max_lines_per_function": 30,
            },
            "secondary": {"require_docstrings": True},
        },
    },
    "functions": {
        "add": {
            "primary": {"max_cyclomatic_complexity": 3},
        },
    },
}


@pytest.fixture
def profiles_path(tmp_path):
    """Provide a temporary profiles YAML file for testing.

    Args:
        tmp_path: Pytest tmp_path fixture.

    Returns:
        Path to the temporary profiles YAML file.
    """
    path = tmp_path / "profiles.yaml"
    path.write_text(yaml.dump(PROFILES_DATA))
    return path


class TestLoadProfiles:
    """Tests for load_profiles."""

    def test_load_profiles_returns_profile_names(self, profiles_path):
        """Test that load_profiles returns all defined profile names.

        Args:
            profiles_path: Path to test profiles YAML.
        """
        profiles = load_profiles(profiles_path)
        assert "default" in profiles
        assert "strict" in profiles

    def test_load_profiles_empty_raises(self, tmp_path):
        """Test that load_profiles raises ValueError for empty files.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        path = tmp_path / "profiles.yaml"
        path.write_text("")
        with pytest.raises(ValueError):
            load_profiles(path)


class TestResolveConstraints:
    """Tests for resolve_constraints."""

    def test_resolve_constraints_strict_profile(self, profiles_path):
        """Test that resolve_constraints applies strict profile values.

        Args:
            profiles_path: Path to test profiles YAML.
        """
        profiles = load_profiles(profiles_path)
        spec = ParsedSpec(
            name="sort",
            description="Sort a list",
            examples=[],
            constraint_profile="strict",
        )
        result = resolve_constraints(spec, profiles)
        assert isinstance(result, TaskConstraints)
        assert result.primary.max_cyclomatic_complexity == 5
        assert result.primary.max_lines_per_function == 30

    def test_resolve_constraints_default_profile(self, profiles_path):
        """Test that resolve_constraints falls back to the default profile.

        Args:
            profiles_path: Path to test profiles YAML.
        """
        profiles = load_profiles(profiles_path)
        spec = ParsedSpec(
            name="unknown_func",
            description="Something",
            examples=[],
        )
        result = resolve_constraints(spec, profiles)
        assert result.primary.max_cyclomatic_complexity == 10

    def test_resolve_constraints_function_override_merges(self, profiles_path):
        """Test that function-level overrides merge with profile constraints.

        Args:
            profiles_path: Path to test profiles YAML.
        """
        profiles = load_profiles(profiles_path)
        spec = ParsedSpec(
            name="add",
            description="Add two numbers",
            examples=[],
            constraint_profile="strict",
        )
        result = resolve_constraints(spec, profiles)
        # strict has cc=5, but functions.add overrides to cc=3
        assert result.primary.max_cyclomatic_complexity == 3
        # strict's other values preserved
        assert result.primary.max_lines_per_function == 30
        assert result.secondary.require_docstrings is True

    def test_resolve_constraints_unknown_profile_raises(self, profiles_path):
        """Test that resolve_constraints raises ValueError for unknown profiles.

        Args:
            profiles_path: Path to test profiles YAML.
        """
        profiles = load_profiles(profiles_path)
        spec = ParsedSpec(
            name="test",
            description="test",
            examples=[],
            constraint_profile="nonexistent",
        )
        with pytest.raises(ValueError):
            resolve_constraints(spec, profiles)

    def test_resolve_constraints_includes_guidance(self, profiles_path):
        """Test that resolve_constraints includes guidance from the profile.

        Args:
            profiles_path: Path to test profiles YAML.
        """
        profiles = load_profiles(profiles_path)
        spec = ParsedSpec(
            name="unknown_func",
            description="Something",
            examples=[],
        )
        result = resolve_constraints(spec, profiles)
        assert "Prefer early returns over nested if/else." in result.guidance
        assert "Avoid inline comments unless ambiguous." in result.guidance

    def test_resolve_constraints_function_guidance_replaces(self, profiles_path):
        """Test that function-level guidance replaces profile guidance.

        Args:
            profiles_path: Path to test profiles YAML.
        """
        profiles = load_profiles(profiles_path)
        profiles["functions"]["add"]["guidance"] = ["Custom guidance for add."]
        spec = ParsedSpec(
            name="add",
            description="Add two numbers",
            examples=[],
        )
        result = resolve_constraints(spec, profiles)
        assert result.guidance == ["Custom guidance for add."]

    def test_resolve_constraints_per_function_profile(self, profiles_path):
        """Test that per-function profiles override task-level profiles.

        Args:
            profiles_path: Path to test profiles YAML.
        """
        profiles = load_profiles(profiles_path)
        spec = ParsedSpec(
            name="auth_system",
            description="Auth module",
            examples=[],
            constraint_profile="default",
            functions=[
                FunctionSpec(name="login", constraint_profile="strict"),
                FunctionSpec(name="logout"),
            ],
        )
        # Resolve for login (has its own profile: strict)
        login_constraints = resolve_constraints(
            spec, profiles, function_name="login"
        )
        assert login_constraints.primary.max_cyclomatic_complexity == 5

        # Resolve for logout (inherits task-level: default)
        logout_constraints = resolve_constraints(
            spec, profiles, function_name="logout"
        )
        assert logout_constraints.primary.max_cyclomatic_complexity == 10


MULTI_FUNCTION_SPEC = {
    "name": "auth_system",
    "description": "Authentication system with login and logout.",
    "constraint_profile": "default",
    "target_files": ["src/auth/handler.py"],
    "functions": [
        {
            "name": "login",
            "description": "Authenticate user",
            "constraint_profile": "strict",
        },
        {
            "name": "logout",
            "description": "End session",
        },
    ],
}


class TestEndToEnd:
    """End-to-end tests for spec-to-constraints resolution."""

    def test_spec_to_constraints_end_to_end(self, tmp_path):
        """Test that spec parsing and constraint resolution work together.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(MULTI_FUNCTION_SPEC))
        profiles_file = tmp_path / "profiles.yaml"
        profiles_file.write_text(yaml.dump(PROFILES_DATA))

        spec = parse_spec(spec_file)
        profiles = load_profiles(profiles_file)

        # login → strict (cc=5)
        login = resolve_constraints(spec, profiles, function_name="login")
        assert login.primary.max_cyclomatic_complexity == 5
        assert login.primary.max_lines_per_function == 30

        # logout → inherits default (cc=10)
        logout = resolve_constraints(spec, profiles, function_name="logout")
        assert logout.primary.max_cyclomatic_complexity == 10
