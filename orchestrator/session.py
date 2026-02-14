"""Session state creation and persistence helpers."""

from pathlib import Path

from orchestrator.models import FunctionProgress, ParsedSpec, SessionState


def create_session(spec: ParsedSpec) -> SessionState:
    """Create initial session state from a parsed specification.

    Args:
        spec: Parsed task specification.

    Returns:
        New session state with one pending entry per function.
    """
    if spec.functions:
        progress = [FunctionProgress(name=func.name) for func in spec.functions]
    else:
        progress = [FunctionProgress(name=spec.name)]
    return SessionState(function_progress=progress)


def save_session(state: SessionState, path: Path) -> None:
    """Persist a session state model to disk as JSON.

    Args:
        state: Session state to persist.
        path: Destination JSON file path.
    """
    path.write_text(state.model_dump_json(indent=2))


def load_session(path: Path) -> SessionState | None:
    """Load a session state model from disk.

    Args:
        path: Session JSON file path.

    Returns:
        Parsed session state, or None when the file does not exist.
    """
    if not path.exists():
        return None
    return SessionState.model_validate_json(path.read_text())
