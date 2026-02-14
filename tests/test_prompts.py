"""Tests for the prompt builders module."""

from orchestrator.prompts import build_exploit_prompt


class TestBuildExploitPrompt:
    def test_build_exploit_prompt_contains_spec_description(self, minimal_spec):
        prompt = build_exploit_prompt(
            "def test_add(): assert add(1, 2) == 3",
            minimal_spec,
        )
        assert minimal_spec.description in prompt

    def test_build_exploit_prompt_includes_test_source(self, minimal_spec):
        test_code = "def test_add():\n    assert add(1, 2) == 3"
        prompt = build_exploit_prompt(test_code, minimal_spec)
        assert "test_add" in prompt
        assert "assert add(1, 2) == 3" in prompt
