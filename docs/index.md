# agentic-tdd

A 2.5-loop system that uses LLM agents to generate tests, critique them, and then implement code that passes those tests.

**Loop 1** — Generate pytest tests from a spec using an LLM agent.

**Loop 1.5** — A red-team critic reviews the tests for exploitability, then actively attempts to write exploit code that passes the tests without implementing the spec.

**Loop 2** — A separate implementing agent writes production code to pass the tests.

## Quick Start

1. Install:

```bash
uv sync
```

2. Install the CLI agents:

```bash
# Claude Code (test generation + critique)
npm install -g @anthropic-ai/claude-code
claude /login

# OpenAI Codex (implementation)
npm install -g @openai/codex
codex auth login
```

3. Write a [spec file](spec-format.md):

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

4. Run:

```bash
atdd run spec.yaml
```

5. Review generated tests, read the critique, and get your implementation. See [Workflow](workflow.md) for the full process.
