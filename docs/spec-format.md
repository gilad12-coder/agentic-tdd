# Spec File Format

Spec files are YAML documents that describe the function(s) you want built. The orchestrator reads a spec and generates tests, critiques, and implementations from it.

## Single-function spec

```yaml
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

## Multi-function spec

```yaml
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

## Field reference

### Top-level fields

| Field | Required | Description |
|---|---|---|
| `name` | yes | Name of the task or function |
| `description` | yes | What the code should do. Supports multi-line. |
| `signature` | no | Python function signature string |
| `examples` | no | List of input/output pairs |
| `constraint_profile` | no | Profile name from profiles.yaml (default: `"default"`) |
| `target_files` | no | List of file paths where code should be written |
| `functions` | no | List of function specs for multi-function tasks |

### Function fields (within `functions:`)

| Field | Required | Description |
|---|---|---|
| `name` | yes | Function name |
| `description` | no | What this specific function does |
| `signature` | no | Python function signature |
| `examples` | no | Input/output examples for this function |
| `constraint_profile` | no | Override the top-level profile for this function |

### Example formats

Standard input/output pair:

```yaml
examples:
  - input: "(1, 2)"
    output: "3"
```

Raw text example (freeform):

```yaml
examples:
  - raw: "Returns empty list for negative input"
```

## How specs are used

1. **Test generation** — the description, signature, and examples are included in the LLM prompt that generates pytest tests.
2. **Critique** — the spec is passed to the red-team critic so it can evaluate whether tests actually enforce the described behavior.
3. **Constraint resolution** — the `constraint_profile` determines which constraints from `profiles.yaml` are applied. See [Constraint Profiles](configuration.md#constraint-profiles).
