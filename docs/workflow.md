# Workflow

## The 2.5-loop system

Most AI code generation is a single pass: prompt in, code out. You hope it works. agentic-tdd adds structure to that process.

```
Spec ──> Loop 1: Generate Tests ──> You Review ──> Loop 1.5: Critique ──> Plan ──> Loop 2: Implement (Docker)
```

Each loop has a distinct role, and you stay in control between them.

---

### Loop 1 — Test generation

An LLM agent reads your spec — the description, signature, examples, and constraints — and generates a pytest test suite.

These tests define the **contract** the implementation must satisfy. The quality of the tests determines the quality of the implementation. Garbage tests produce garbage code.

---

### Your review

You see the generated tests and choose:

- **`a`** (approve) — accept the tests as-is
- **`e`** (edit) — open in `$EDITOR`, modify, then review again
- **`r`** (regenerate) — discard and generate new tests from scratch

!!! tip
    This is the most important step. The tests are the specification. If you approve weak tests, everything downstream will be weak too.

---

### Loop 1.5 — Red-team critique

After you approve, a critic agent attacks the tests in two phases.

**Passive analysis** identifies weaknesses without writing code:

- **Exploit vectors** — ways an implementation could game the tests
- **Missing edge cases** — scenarios the tests don't cover
- **Suggested counter tests** — additional tests to harden coverage

**Active exploit attempt** — the critic writes a deliberately cheating implementation and runs it against the tests with pytest. The cheat uses hardcoded returns, input sniffing, lookup tables — anything that passes the tests without actually implementing the spec.

!!! warning
    If the exploit passes, the tests have real gaps. The exploit code is displayed so you can see exactly how the tests were gamed.

---

### Plan generation

After all functions have been through the generate-critique loop, a structured `plan.md` is auto-generated. The plan includes:

- Project name, description, and target files
- Per-function: signature, description, examples, constraints, and critique findings
- Test file paths for the implementation agent to run

This gives the implementation agent complete context about what to build and what quality rules to follow.

---

### Loop 2 — Implementation

A separate implementing agent receives the plan and locked test files, then writes production code inside a **Docker container** for full isolation. The implementation loop:

1. Writes approved tests and `plan.md` to the workspace
2. Runs the implementation agent (on host — needs API keys)
3. Runs pytest inside a Docker container (isolates untrusted code)
4. If tests fail, feeds error output back to the agent and retries
5. Repeats until all tests pass or max retries exhausted

The implementation must pass both the tests and the constraints.

!!! info
    If Docker is unavailable, the system falls back to running pytest directly on the host.

---

## Running

```bash
# Interactive — review tests and critique manually
atdd run spec.yaml

# Auto-accept tests and critique
atdd run spec.yaml -y

# Auto-accept and auto-implement in Docker
atdd run spec.yaml -y --implement

# Fine-grained: auto-accept tests only, manual critique
atdd run spec.yaml --auto-tests

# Custom profiles and session path
atdd run spec.yaml --profiles constraints/profiles.yaml --session .session.json

# Check progress
atdd status

# Run implementation separately on a completed session
atdd implement --spec spec.yaml

# Implementation without Docker (runs pytest on host)
atdd implement --spec spec.yaml --no-docker
```

---

## Session management

Progress is saved after each step. If the process is interrupted, re-running `atdd run` resumes from where it left off.

The session file (default: `.session.json`) tracks each function's status:

| Status | Meaning |
|---|---|
| `pending` | Not started |
| `tests_generated` | Tests generated, awaiting review |
| `tests_approved` | Tests approved by human |
| `critiqued` | Critique completed |
| `done` | Implementation complete |
