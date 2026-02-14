# agentic-tdd

A 2.5-loop system that uses LLM agents to generate tests, critique them, and then implement code that passes those tests.

**Loop 1** — Generate pytest tests from a spec using an LLM agent.
**Loop 1.5** — A red-team critic reviews the tests for exploitability, then actively attempts to write exploit code that passes the tests without implementing the spec.
**Loop 2** — A separate implementing agent writes production code to pass the tests.

## Install

```bash
uv sync
```

## Prerequisites

The CLI agents must be installed and authenticated separately:

```bash
# Claude Code (test generation + critique)
npm install -g @anthropic-ai/claude-code
claude /login

# OpenAI Codex (implementation)
npm install -g @openai/codex
codex auth login
```

## Usage

1. Write a [spec file](docs/spec-format.md):

```yaml
name: add
description: |
  Adds two integers and returns their sum.
signature: "add(a: int, b: int) -> int"
examples:
  - input: "(1, 2)"
    output: "3"
constraint_profile: default
target_files:
  - "src/add.py"
```

2. Run the orchestrator:

```bash
atdd run spec.yaml
```

3. Review generated tests, read the critique, and get your implementation.

See [Workflow](docs/workflow.md) for the full process.

## Documentation

| Doc | Description |
|-----|-------------|
| [Workflow](docs/workflow.md) | The 2.5-loop system, review process, session management |
| [Spec Format](docs/spec-format.md) | YAML spec file reference |
| [Configuration](docs/configuration.md) | Environment variables, constraint profiles, CLI options |
| [Constraints](docs/constraints.md) | All 34 available constraints with examples and quick-copy profiles |

## Running Tests

```bash
uv run pytest tests/ -v
```

