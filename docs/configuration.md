# Configuration

## Environment variables

The orchestrator reads agent and budget settings from environment variables. All have sensible defaults — you don't need to set any of them to get started.

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

---

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

---

## Constraint profiles

Profiles define the quality rules applied to generated code. They live in a YAML file (default: `constraints/profiles.yaml`).

```yaml title="constraints/profiles.yaml"
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

**`primary`** — Hard limits. Code must pass all of these. If any fail, the code is rejected and secondary constraints are not checked.

**`secondary`** — Style and quality rules. Only evaluated if all primary constraints pass. Failures are reported but may be advisory depending on your workflow.

**`guidance`** — Freeform strings passed to the LLM in the prompt. Not mechanically checked. Use these for preferences that can't be expressed as static analysis rules.

!!! info
    For all 34 available constraints, see the [Constraint Reference](constraints.md).

### Function-level overrides

You can override constraints for specific functions:

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

Function overrides **merge** with the profile for primary/secondary. Guidance uses **replace** semantics — if a function defines guidance, it fully replaces the profile's guidance.

### Profile resolution order

1. Look up the `constraint_profile` name from the spec (default: `"default"`)
2. Load that profile from `profiles.yaml`
3. If the function name has an entry under `functions:`, merge those overrides
4. The resolved constraints are passed to the static analysis engine

---

## CLI options

### `atdd run`

```
atdd run spec.yaml [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--profiles` | `constraints/profiles.yaml` | Path to constraint profiles file |
| `--session` | `.session.json` | Path to session state file |
| `-y` / `--auto` | off | Auto-accept both tests and critique |
| `--auto-tests` | off | Auto-approve generated tests without prompting |
| `--auto-critique` | off | Auto-accept critique without prompting |
| `--implement` | off | Auto-run implementation in Docker after all functions complete |

### `atdd implement`

Run implementation separately on a completed session.

```
atdd implement --spec spec.yaml [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--spec` | *(required)* | Path to spec YAML file |
| `--profiles` | `constraints/profiles.yaml` | Path to constraint profiles file |
| `--session` | `.session.json` | Path to session state file |
| `--no-docker` | off | Run pytest on host instead of in Docker |

### `atdd status`

```
atdd status [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--session` | `.session.json` | Path to session state file |

---

## Session persistence

The orchestrator saves progress after each function completes. If interrupted, re-running `atdd run` resumes from where it left off.

Session state is stored as JSON at the path specified by `--session`.

```bash
# Check where you left off
atdd status
```
