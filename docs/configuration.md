# Configuration

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GENERATION_AGENT` | `claude` | Agent for test generation (`claude` or `codex`) |
| `GENERATION_MODEL` | `claude-opus-4-6` | Model for test generation |
| `CRITIC_AGENT` | `claude` | Agent for red-team critique |
| `CRITIC_MODEL` | `claude-opus-4-6` | Model for critique |
| `IMPLEMENTATION_AGENT` | `codex` | Agent for code implementation |
| `IMPLEMENTATION_MODEL` | `gpt-5.3-codex` | Model for implementation |
| `MAX_ITERATIONS` | `10` | Max regeneration attempts per function |
| `MAX_BUDGET_USD` | `5.0` | Budget cap per agent call |

## Prerequisites

The CLI agents must be installed and authenticated separately.

**Claude Code** (test generation + critique):

```bash
npm install -g @anthropic-ai/claude-code
claude /login
```

**OpenAI Codex** (implementation):

```bash
npm install -g @openai/codex
codex auth login
```

## Constraint profiles

Profiles are defined in a YAML file (default: `constraints/profiles.yaml`) and map profile names to sets of constraints.

```yaml
profiles:
  default:
    primary:
      max_cyclomatic_complexity: 10
    secondary:
      require_docstrings: true

  strict:
    primary:
      max_cyclomatic_complexity: 5
      max_lines_per_function: 30
      max_time_complexity: "O(n)"
      no_eval: true
      no_exec: true
      no_bare_except: true
    secondary:
      require_docstrings: true
      require_type_annotations: true
    guidance:
      - "Prefer early returns over nested conditionals."
      - "Avoid inline comments unless the logic is ambiguous."
```

### Constraint gates

Each profile has three sections:

- **`primary`** — hard limits. Code must pass all of these. If any fail, the code is rejected and secondary constraints are not checked.
- **`secondary`** — style and quality rules. Only evaluated if all primary constraints pass. Failures are reported but may be advisory depending on your workflow.
- **`guidance`** — freeform strings passed to the LLM in the prompt. Not mechanically checked. Use these for preferences that can't be expressed as static analysis rules.

### Function-level overrides

You can override constraints per function:

```yaml
profiles:
  default:
    primary:
      max_cyclomatic_complexity: 10

functions:
  login:
    primary:
      max_lines_per_function: 20
    guidance:
      - "Never log passwords."
```

Function overrides **merge** with the profile for primary/secondary (the function's constraints are added to or override the profile's). Guidance uses **replace** semantics — if a function defines guidance, it fully replaces the profile's guidance.

### Profile resolution order

1. Look up the `constraint_profile` name from the spec (default: `"default"`)
2. Load that profile from `profiles.yaml`
3. If the function name has an entry under `functions:`, merge those overrides
4. The resolved `TaskConstraints` is passed to the static analysis engine

## CLI options

```
atdd run spec.yaml [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--profiles` | `constraints/profiles.yaml` | Path to constraint profiles file |
| `--session` | `.session.json` | Path to session state file |

```
atdd status [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--session` | `.session.json` | Path to session state file |

## Session persistence

The orchestrator saves progress after each function completes. If interrupted, re-running `atdd run` resumes from where it left off. Session state is stored as JSON at the path specified by `--session`.

Use `atdd status` to view a table of all functions with their current progress.
