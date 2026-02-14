# agentic-tdd

**Agentic test-driven development. Write a spec, get tested code.**

You describe what a function should do. LLM agents generate tests, try to break them, and then write the implementation — all under mechanical quality constraints you control.

---

## Why?

LLMs are good at writing code. They're bad at writing *correct* code. Tests help, but LLM-generated tests are often shallow — a cheating implementation can pass them with hardcoded returns.

agentic-tdd fixes this with a **2.5-loop system**:

- **Loop 1** — An LLM generates pytest tests from your spec.
- **You review** — Approve, edit, or regenerate the tests.
- **Loop 1.5** — A red-team critic actively tries to *cheat* the tests. If it succeeds, you know your tests are weak.
- **Plan** — A structured implementation plan is auto-generated from the spec, constraints, and critique findings.
- **Loop 2** — A separate LLM writes production code that passes the hardened tests inside a Docker container, retrying with error feedback until all tests pass.

The result: code that is tested, critiqued, and constrained — not just "it compiles."

---

## How it works

```
Spec ──> Generate Tests ──> You Review ──> Critic Attacks ──> Plan ──> Implement (Docker)
```

You write a YAML spec describing the function. The system does the rest.

```yaml
name: add
description: |
  Adds two integers and returns their sum.
signature: "add(a: int, b: int) -> int"
examples:
  - input: "(1, 2)"
    output: "3"
```

```bash
# Interactive
atdd run spec.yaml

# Full auto with Docker implementation
atdd run spec.yaml -y --implement
```

That's it. See the [Tutorial](tutorial.md) to walk through a complete example.

---

## Features

**Test generation from specs** — Describe what you want in YAML. Get a full pytest suite.

**Red-team critique** — A critic agent finds exploit vectors in your tests, then *proves* they're weak by writing a cheating implementation that passes them.

**Docker sandbox** — Implementation tests run in an isolated Docker container. Untrusted generated code never touches your host. Falls back to host pytest if Docker is unavailable.

**Auto-generated implementation plan** — A structured `plan.md` is built from the spec, constraints, and critique findings, giving the implementation agent full context.

**34 static analysis constraints** — Complexity limits, correctness checks, security rules, style enforcement. All checked via AST — no runtime needed. [See the full list](constraints.md).

**Two-gate constraint system** — Primary constraints are hard blockers. Secondary constraints are advisory. Guidance strings are passed to the LLM but not mechanically checked.

**Auto-accept mode** — Use `-y` to auto-accept tests and critique, or fine-tune with `--auto-tests` and `--auto-critique`. Add `--implement` to trigger implementation automatically.

**Session persistence** — Progress saves after each step. Interrupted? Just re-run.

**Pluggable agents** — Use Claude for test generation, Codex for implementation, or swap them. [Configure via environment variables](configuration.md).

---

## Install

```bash
uv sync
```

You'll also need the CLI agents installed separately:

```bash
# Claude Code (test generation + critique)
npm install -g @anthropic-ai/claude-code
claude /login

# OpenAI Codex (implementation)
npm install -g @openai/codex
codex auth login

# Docker (optional — sandbox isolation for implementation tests)
# https://docs.docker.com/get-docker/
```

!!! tip
    See [Configuration](configuration.md) for all environment variables and CLI options.

---

## Next steps

<div class="grid cards" markdown>

- **[Tutorial](tutorial.md)** — Walk through a complete spec-to-implementation example.
- **[Spec Format](spec-format.md)** — YAML spec file reference.
- **[Constraints](constraints.md)** — All 34 constraints with examples and quick-copy profiles.
- **[Configuration](configuration.md)** — Environment variables, constraint profiles, CLI options.

</div>
