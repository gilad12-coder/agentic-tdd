# CLAUDE.md

## Task

You are updating the `orchestrator/` package. Your sole objective: make ALL tests pass.

## Rules

1. **Tests are read-only.** Do not modify anything under `tests/`. They are the spec.
2. **Read `IMPLEMENTATION_PLAN.md`** at the project root for the full guide.
3. **Start at Step 16.** Steps 1–15 are already implemented and passing.
4. **Run tests after each module:** `pytest tests/ -m "not llm" -v`
5. **All code must have Google-style docstrings** on every function and class — summary line + `Args:` section (if params) + `Returns:` section (if returns a value).
6. **Keep functions under 80 lines** and cyclomatic complexity under 15.
7. **Keep going until all tests pass.** You are never done until the test suite is green.
8. **Do NOT modify `models.py` or `config.py`** — the new fields are already there.

## What to Update

- `orchestrator/display.py` — NEW FILE: all rich formatting functions (Step 16)
- `orchestrator/__main__.py` — restructure to subparsers, add status command (Step 17)
- `orchestrator/cli_runner.py` — add timeout/missing-binary error handling (Step 18)
- `orchestrator/critic.py` — add JSON extraction fallback in `parse_critique` (Step 19)
- `orchestrator/loop.py` — use display functions, add edit flow, error handling (Step 20)

## Quick Commands

```bash
pip install -e ".[dev]"
pytest tests/ -m "not llm" -v
pytest tests/test_self_constraints.py -v
```
