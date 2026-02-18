# Spec Format

Spec files are YAML documents that describe the function(s) you want built. The orchestrator reads a spec and generates tests, critiques, and implementations from it.

---

## Single-function spec

The simplest case — one function, one file:

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
constraint_profile: strict
target_files:
  - "src/add.py"
```

The `description` is the most important field. It tells the test generator *what* to test. Be specific — vague descriptions produce vague tests.

---

## Multi-function spec

For related functions that belong together:

```yaml title="spec.yaml"
name: auth_system
description: Authentication system with login and logout.
constraint_profile: default
target_files:
  - "src/auth/handler.py"
functions:
  - name: login
    description: Authenticate user
    signature: "login(username: str, password: str) -> str"
    examples:
      - input: '("admin", "pass")'
        output: '"token"'
    constraint_profile: strict
  - name: logout
    description: End session
    signature: "logout(token: str) -> bool"
    examples:
      - input: '("token123")'
        output: "True"
```

Each function can override the top-level `constraint_profile`. Functions without their own profile inherit the top-level one.

---

## Field reference

### Top-level fields

| Field | Required | Description |
|---|---|---|
| `name` | yes | Name of the task or function |
| `description` | yes | What the code should do. Supports multi-line. |
| `signature` | no | Python function signature string |
| `examples` | no | List of input/output pairs |
| `public_evals` | no | Explicit public eval cases (defaults to `examples` if omitted) |
| `hidden_evals` | no | Secret eval cases the implementation must pass but never sees |
| `constraint_profile` | no | Profile name from profiles.yaml (default: `"default"`) |
| `target_files` | no | List of file paths where code should be written |
| `functions` | no | List of function specs for multi-function tasks |

### Function fields

| Field | Required | Description |
|---|---|---|
| `name` | yes | Function name |
| `description` | no | What this specific function does |
| `signature` | no | Python function signature |
| `examples` | no | Input/output examples for this function |
| `public_evals` | no | Explicit public eval cases for this function |
| `hidden_evals` | no | Secret eval cases for this function |
| `constraint_profile` | no | Override the top-level profile for this function |

---

## Example formats

Standard input/output pair:

```yaml
examples:
  - input: "(1, 2)"
    output: "3"
```

Freeform description:

```yaml
examples:
  - raw: "Returns empty list for negative input"
```

!!! tip
    Concrete input/output examples produce better tests than freeform descriptions. Use `raw` only when the behavior is hard to express as a single return value.

---

## Public and hidden evals

Evals are input/output pairs used to verify the implementation. They come in two flavors:

**Public evals** are visible to the test generator and included in its prompt. By default, `examples` are used as public evals. If you provide an explicit `public_evals` field, it takes precedence:

```yaml
examples:
  - input: "(1, 2)"
    output: "3"
public_evals:
  - input: "(1, 2)"
    output: "3"
  - input: "(0, 0)"
    output: "0"
```

**Hidden evals** are secret test cases that the implementation must pass but the agent never sees. They prevent hardcoded implementations and verify genuine correctness:

```yaml
hidden_evals:
  - input: "(100, 200)"
    output: "300"
  - input: "(-5, -3)"
    output: "-8"
```

Hidden evals run in a second verification phase after the public tests pass. Failure feedback is redacted — the implementation agent learns that hidden cases failed but never sees the actual inputs or outputs.

!!! tip
    Use hidden evals for edge cases you want to guarantee without revealing them to the agent. This makes it impossible to pass by hardcoding return values.

---

## How specs are used

1. **Test generation** — the description, signature, and examples are included in the LLM prompt that generates pytest tests.
2. **Critique** — the spec is passed to the red-team critic so it can evaluate whether tests actually enforce the described behavior.
3. **Constraint resolution** — the `constraint_profile` determines which constraints are applied. See [Constraint Profiles](configuration.md#constraint-profiles).
4. **Plan generation** — after the critique loop, a `plan.md` is auto-generated for the implementation agent. It includes every non-None field from the spec: signatures, descriptions, examples, all resolved constraints (primary, secondary, guidance), and critique findings. The implementation agent receives the complete picture of what to build.
