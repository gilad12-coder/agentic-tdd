# Workflow

## The 2.5-loop system

```
Spec ──> Loop 1: Generate Tests ──> Human Review ──> Loop 1.5: Critique ──> Loop 2: Implement
```

### Loop 1 — Test generation

An LLM agent reads your spec (description, signature, examples, constraints) and generates a pytest test suite. The generated tests define the contract that the implementation must satisfy.

### Human review

You review the generated tests and choose:

- **`a`** (approve) — accept the tests as-is
- **`e`** (edit) — open in `$EDITOR`, modify, then review again
- **`r`** (regenerate) — discard and generate new tests from scratch

### Loop 1.5 — Red-team critique

After you approve, a critic agent reviews the tests in two phases:

**Passive analysis** identifies weaknesses:
- **Exploit vectors** — ways an implementation could game the tests
- **Missing edge cases** — scenarios the tests don't cover
- **Suggested counter tests** — additional tests to harden coverage

**Active exploit attempt** — the critic writes a deliberately cheating implementation (hardcoded returns, input sniffing, lookup tables) and runs it against the approved tests with pytest. If the exploit passes, the tests are flagged as weak and the exploit code is displayed.

### Loop 2 — Implementation

A separate implementing agent receives the locked test files and writes production code to make them pass. Constraint checks are applied to the generated code.

## Running

```bash
# Run the full workflow
atdd run spec.yaml

# Run with custom profiles and session path
atdd run spec.yaml --profiles constraints/profiles.yaml --session .session.json

# Check progress
atdd status
```

## Session management

Progress is saved after each function completes. If the process is interrupted, re-running `atdd run` resumes from where it left off.

The session file (default: `.session.json`) tracks each function's status:

| Status | Meaning |
|---|---|
| `pending` | Not started |
| `tests_generated` | Tests generated, awaiting review |
| `tests_approved` | Tests approved by human |
| `critiqued` | Critique completed |
| `done` | Implementation complete |
