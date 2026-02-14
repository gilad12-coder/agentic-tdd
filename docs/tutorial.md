# Tutorial

This walks you through a complete run — from writing a spec to getting tested, constrained code.

---

## 1. Write a spec

Create a YAML file describing the function you want:

```yaml title="spec.yaml"
name: add
description: |
  Adds two integers and returns their sum.
  - Works with negative numbers
  - Works with zero
signature: "add(a: int, b: int) -> int"
examples:
  - input: "(1, 2)"
    output: "3"
  - input: "(-1, 1)"
    output: "0"
constraint_profile: default
target_files:
  - "src/add.py"
```

The `description` and `examples` tell the test generator what to test. The `signature` gives it the function shape. The `constraint_profile` controls what quality rules the implementation must satisfy.

!!! info
    For multi-function specs or all available fields, see [Spec Format](spec-format.md).

---

## 2. Set up constraints

Create a profiles file that defines your quality rules:

```yaml title="constraints/profiles.yaml"
profiles:
  default:
    primary:
      max_cyclomatic_complexity: 10
      no_bare_except: true
      no_eval: true
    secondary:
      require_docstrings: true
```

**Primary** constraints are hard blockers — the implementation must pass all of them. **Secondary** constraints are checked only if primary passes, and are advisory.

!!! tip
    Don't want to write your own? Copy one of the [quick-copy profiles](constraints.md#quick-copy-profiles) — minimal, recommended, or strict.

---

## 3. Run the orchestrator

```bash
# Interactive mode — you review each step
atdd run spec.yaml

# Or fully automated with implementation
atdd run spec.yaml -y --implement
```

The orchestrator starts **Loop 1** — it calls the test generation agent and shows you the result.

---

## 4. Review the tests

The generated tests appear with syntax highlighting. You choose:

```
Review: [a]pprove / [e]dit / [r]egenerate:
```

- **`a`** — accept the tests as-is
- **`e`** — open in `$EDITOR`, modify, then review again
- **`r`** — discard and regenerate from scratch

!!! tip
    Read the tests carefully. These define the contract your implementation must satisfy. If the tests are weak, the implementation will be too.

---

## 5. Read the critique

After you approve, **Loop 1.5** kicks in. A red-team critic reviews your tests in two phases.

**Passive analysis** identifies weaknesses:

- **Exploit vectors** — ways an implementation could game the tests
- **Missing edge cases** — scenarios the tests don't cover
- **Suggested counter tests** — additional tests to harden coverage

**Active exploit attempt** — the critic writes a deliberately cheating implementation (hardcoded returns, input sniffing, lookup tables) and runs it against your approved tests. If the exploit passes, you know the tests have gaps.

This is the key insight: if a cheating implementation can pass your tests, a real implementation might pass them without actually being correct either.

---

## 6. Get the implementation

After all functions pass the critique loop, a `plan.md` is auto-generated containing the full spec, constraints, and critique findings.

**Loop 2** takes the plan and locked tests, then generates production code. The implementation agent runs on the host, while pytest runs inside a Docker container for isolation. If tests fail, the errors are fed back to the agent for another attempt.

The implementation must:

1. Pass all tests (verified in Docker)
2. Pass all primary constraints
3. Report on secondary constraints

The result is written to the `target_files` you specified in the spec.

If you didn't use `--implement` during `atdd run`, you can trigger implementation separately:

```bash
atdd implement --spec spec.yaml
```

---

## 7. Check status

If the process is interrupted at any point, check where you left off:

```bash
atdd status
```

Re-running `atdd run spec.yaml` resumes from where it stopped. Progress is saved after each step.

---

## What's next?

- **[Spec Format](spec-format.md)** — multi-function specs, all available fields
- **[Constraints](constraints.md)** — the full list of 34 constraints you can apply
- **[Configuration](configuration.md)** — swap agents, set budgets, customize profiles
