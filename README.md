# agentic-tdd

**Agentic test-driven development. Write a spec, get tested code.**

---

**Documentation**: <a href="https://gilad12-coder.github.io/agentic-tdd" target="_blank">https://gilad12-coder.github.io/agentic-tdd</a>

**Source Code**: <a href="https://github.com/gilad12-coder/agentic-tdd" target="_blank">https://github.com/gilad12-coder/agentic-tdd</a>

---

You describe what a function should do. LLM agents generate tests, try to break them, and then write the implementation — all under mechanical quality constraints you control.

## Key Features

- **Tested by default** — every function starts with a generated pytest suite, not an afterthought.
- **Red-team critiqued** — a critic agent actively tries to cheat the tests. If it can pass them with hardcoded returns, you know they're weak.
- **Docker sandbox** — implementation tests run in an isolated Docker container. Untrusted generated code never touches your host.
- **34 static analysis constraints** — complexity limits, correctness checks, security rules, style enforcement. All via AST, no runtime needed.
- **Human in the loop** — you review and approve tests before anything gets implemented. Or use `-y` to auto-accept everything.
- **Session persistence** — interrupted? Re-run and pick up where you left off.
- **Public + hidden eval split** — generation sees only public evals, while final verification can enforce hidden evals.
- **Pluggable agents** — Claude for test generation, Codex for implementation, or swap them.

## How It Works

```
Spec ──> Generate Tests ──> You Review ──> Critic Attacks ──> Plan ──> Implement (Docker)
```

**Loop 1** — An LLM generates pytest tests from your spec.

**Loop 1.5** — A red-team critic attacks the tests. It writes a cheating implementation and runs it. If the cheat passes, the tests have gaps.

**Plan** — A structured `plan.md` is auto-generated from the spec, constraints, and critique findings.

**Loop 2** — A separate LLM writes production code that passes the hardened tests inside a Docker container, retrying with error feedback until all tests pass.

## Requirements

- Python 3.12+
- <a href="https://github.com/anthropics/claude-code" target="_blank">Claude Code</a> (test generation + critique)
- <a href="https://github.com/openai/codex" target="_blank">OpenAI Codex</a> (implementation)
- <a href="https://docs.docker.com/get-docker/" target="_blank">Docker</a> (sandbox isolation for implementation tests — optional, falls back to host pytest)

## Installation

```bash
uv sync
```

Install and authenticate the CLI agents:

```bash
npm install -g @anthropic-ai/claude-code
claude /login

npm install -g @openai/codex
codex auth login
```

## Example

### Write a spec

```yaml
name: add
description: |
  Adds two integers and returns their sum.
  - Works with negative numbers
  - Works with zero
signature: "add(a: int, b: int) -> int"
public_evals:
  - input: "(1, 2)"
    output: "3"
hidden_evals:
  - input: "(100, 23)"
    output: "123"
constraint_profile: default
target_files:
  - "src/add.py"
```

### Run it

```bash
# Interactive — review tests and critique manually
atdd run spec.yaml

# Auto-accept everything and implement in Docker
atdd run spec.yaml -y --implement

# Run implementation separately after a completed session
atdd implement --spec spec.yaml
```

### Check status

```bash
atdd status
```

## Dependencies

- <a href="https://docs.pydantic.dev/" target="_blank">Pydantic</a> — data models and validation
- <a href="https://radon.readthedocs.io/" target="_blank">Radon</a> — cyclomatic complexity analysis
- <a href="https://rich.readthedocs.io/" target="_blank">Rich</a> — terminal output

## License

MIT
