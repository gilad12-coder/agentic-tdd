import pytest
import yaml

from orchestrator.spec_intake import parse_spec
from orchestrator.models import FunctionSpec, ParsedSpec


FULL_SPEC = {
    "name": "add",
    "description": (
        "Adds two integers and returns their sum.\n"
        "- Returns the sum of a and b\n"
        "- Works with negative numbers\n"
        "- Works with zero"
    ),
    "signature": "add(a: int, b: int) -> int",
    "examples": [
        {"input": "(1, 2)", "output": "3"},
        {"input": "(0, 0)", "output": "0"},
        {"input": "(-1, 1)", "output": "0"},
    ],
    "constraint_profile": "strict",
    "target_files": ["src/add.py"],
}

MULTI_FUNCTION_SPEC = {
    "name": "auth_system",
    "description": "Authentication system with login and logout.",
    "constraint_profile": "default",
    "target_files": ["src/auth/handler.py"],
    "functions": [
        {
            "name": "login",
            "description": "Authenticate user",
            "signature": "login(username: str, password: str) -> str",
            "examples": [{"input": '("admin", "pass")', "output": '"token"'}],
            "constraint_profile": "strict",
        },
        {
            "name": "logout",
            "description": "End session",
            "signature": "logout(token: str) -> bool",
            "examples": [{"input": '("token123")', "output": "True"}],
        },
    ],
}

MINIMAL_SPEC = {
    "name": "multiply",
    "description": "Multiply two numbers.",
}

PUBLIC_HIDDEN_SPEC = {
    "name": "divide",
    "description": "Divide numbers safely.",
    "public_evals": [{"input": "(6, 3)", "output": "2"}],
    "hidden_evals": [{"input": "(10, 2)", "output": "5"}],
    "target_files": ["src/divide.py"],
}

MIXED_PRECEDENCE_SPEC = {
    "name": "pow2",
    "description": "Square numbers.",
    "examples": [{"input": "(2)", "output": "4"}],
    "public_evals": [{"input": "(3)", "output": "9"}],
}

FUNCTION_EVAL_SPEC = {
    "name": "auth_system",
    "description": "Authentication system.",
    "public_evals": [{"input": '("seed")', "output": '"seed-token"'}],
    "hidden_evals": [{"input": '("hidden")', "output": '"hidden-token"'}],
    "functions": [
        {
            "name": "login",
            "public_evals": [{"input": '("admin")', "output": '"token"'}],
            "hidden_evals": [{"input": '("root")', "output": '"root-token"'}],
        }
    ],
}


class TestParseSpec:
    """Tests for parse_spec."""

    def test_parse_spec_extracts_name(self, tmp_path):
        """Test that parse_spec extracts the spec name from YAML.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(FULL_SPEC))
        result = parse_spec(spec_file)
        assert isinstance(result, ParsedSpec)
        assert result.name == "add"

    def test_parse_spec_extracts_functions_list(self, tmp_path):
        """Test that parse_spec extracts the functions list from YAML.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(MULTI_FUNCTION_SPEC))
        result = parse_spec(spec_file)
        assert len(result.functions) == 2
        assert isinstance(result.functions[0], FunctionSpec)
        assert result.functions[0].name == "login"
        assert result.functions[0].constraint_profile == "strict"
        assert result.functions[1].name == "logout"
        assert result.functions[1].constraint_profile is None

    def test_parse_spec_defaults_with_minimal_input(self, tmp_path):
        """Test that parse_spec applies defaults for minimal spec input.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(MINIMAL_SPEC))
        result = parse_spec(spec_file)
        assert result.name == "multiply"
        assert len(result.description) > 0
        assert result.signature is None
        assert result.examples == []
        assert result.constraint_profile == "default"
        assert result.functions == []

    def test_parse_spec_empty_file_raises_value_error(self, tmp_path):
        """Test that parse_spec raises ValueError for empty files.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("")
        with pytest.raises(ValueError):
            parse_spec(spec_file)

    def test_parse_spec_public_and_hidden_evals(self, tmp_path):
        """Test that parse_spec extracts top-level public and hidden evals.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(PUBLIC_HIDDEN_SPEC))
        result = parse_spec(spec_file)
        assert result.public_evals == [{"input": "(6, 3)", "output": "2"}]
        assert result.hidden_evals == [{"input": "(10, 2)", "output": "5"}]

    def test_parse_spec_public_evals_precedence(self, tmp_path):
        """Test that public_evals override examples when both are set.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(MIXED_PRECEDENCE_SPEC))
        result = parse_spec(spec_file)
        assert result.public_evals == [{"input": "(3)", "output": "9"}]
        assert result.examples == result.public_evals

    def test_parse_spec_function_level_public_and_hidden_evals(self, tmp_path):
        """Test that function-level public/hidden evals are parsed.

        Args:
            tmp_path: Pytest tmp_path fixture.
        """
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(FUNCTION_EVAL_SPEC))
        result = parse_spec(spec_file)
        assert len(result.functions) == 1
        assert result.functions[0].public_evals == [
            {"input": '("admin")', "output": '"token"'}
        ]
        assert result.functions[0].hidden_evals == [
            {"input": '("root")', "output": '"root-token"'}
        ]
