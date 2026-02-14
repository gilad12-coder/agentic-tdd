"""CLI entry point for running orchestrator sessions."""

import argparse
from pathlib import Path

from orchestrator.display import display_error, display_status_table
from orchestrator.loop import run_session
from orchestrator.session import load_session


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser with run and status subcommands.

    Returns:
        Configured argument parser instance.
    """
    parser = argparse.ArgumentParser(prog="atdd")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run_parser = subcommands.add_parser("run")
    run_parser.add_argument("spec_path")
    run_parser.add_argument("--profiles", default="constraints/profiles.yaml")
    run_parser.add_argument("--session", default=".session.json")

    status_parser = subcommands.add_parser("status")
    status_parser.add_argument("--session", default=".session.json")
    return parser


def show_status(session_path: Path) -> None:
    """Load and display a persisted session status table.

    Args:
        session_path: Location of the session state file.
    """
    state = load_session(session_path)
    if state is None:
        display_error(f"No session found at {session_path}")
        raise SystemExit(1)
    display_status_table(state)


def main(argv: list[str] | None = None) -> None:
    """Parse CLI args and dispatch to run or status behavior.

    Args:
        argv: Optional argument vector for testing.
    """
    args = build_parser().parse_args(argv)

    if args.command == "run":
        spec_path = Path(args.spec_path)
        if not spec_path.exists():
            display_error(f"Spec file not found: {spec_path}")
            raise SystemExit(1)
        run_session(
            spec_path=spec_path,
            profiles_path=Path(args.profiles),
            session_path=Path(args.session),
        )
    elif args.command == "status":
        show_status(Path(args.session))


if __name__ == "__main__":
    main()
