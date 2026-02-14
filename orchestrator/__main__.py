"""CLI entry point for running orchestrator sessions."""

import argparse
from pathlib import Path

from orchestrator.display import (
    display_docker_status,
    display_error,
    display_implementation_result,
    display_status_table,
)
from orchestrator.loop import run_implementation, run_session
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
    run_parser.add_argument(
        "-y", "--auto", action="store_true",
        help="Auto-accept all reviews (tests + critique)",
    )
    run_parser.add_argument(
        "--auto-tests", action="store_true",
        help="Auto-approve generated tests without prompting",
    )
    run_parser.add_argument(
        "--auto-critique", action="store_true",
        help="Auto-accept critique without prompting",
    )
    run_parser.add_argument(
        "--implement", action="store_true",
        help="Auto-run implementation after test generation completes",
    )

    status_parser = subcommands.add_parser("status")
    status_parser.add_argument("--session", default=".session.json")

    impl_parser = subcommands.add_parser("implement")
    impl_parser.add_argument("--spec", required=True, help="Path to spec YAML")
    impl_parser.add_argument("--profiles", default="constraints/profiles.yaml")
    impl_parser.add_argument("--session", default=".session.json")
    impl_parser.add_argument(
        "--no-docker", action="store_true",
        help="Run pytest on host instead of in Docker",
    )
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
        auto_all = getattr(args, "auto", False)
        run_session(
            spec_path=spec_path,
            profiles_path=Path(args.profiles),
            session_path=Path(args.session),
            auto_tests=auto_all or getattr(args, "auto_tests", False),
            auto_critique=auto_all or getattr(args, "auto_critique", False),
            auto_implement=getattr(args, "implement", False),
        )
    elif args.command == "status":
        show_status(Path(args.session))
    elif args.command == "implement":
        run_implement(
            spec_path=Path(args.spec),
            profiles_path=Path(args.profiles),
            session_path=Path(args.session),
            use_docker=not getattr(args, "no_docker", False),
        )


def run_implement(
    spec_path: Path,
    profiles_path: Path,
    session_path: Path,
    use_docker: bool = True,
) -> None:
    """Load a completed session and run the implementation agent.

    Args:
        spec_path: Path to the task specification YAML file.
        profiles_path: Path to the constraints profiles YAML file.
        session_path: Path to persisted session JSON state.
        use_docker: When True, verify tests inside a Docker container.
    """
    from orchestrator.config import Config
    from orchestrator.constraint_loader import load_profiles, resolve_constraints
    from orchestrator.spec_intake import parse_spec

    state = load_session(session_path)
    if state is None:
        display_error(f"No session found at {session_path}")
        raise SystemExit(1)

    if not spec_path.exists():
        display_error(f"Spec file not found: {spec_path}")
        raise SystemExit(1)

    spec = parse_spec(spec_path)
    profiles = load_profiles(profiles_path)
    config = Config()

    if use_docker:
        from orchestrator.sandbox import check_docker_available

        available = check_docker_available()
        display_docker_status(available)
        if not available:
            use_docker = False

    constraints_map = {
        p.name: resolve_constraints(spec, profiles, p.name)
        for p in state.function_progress
    }
    success = run_implementation(
        state, config,
        spec=spec, constraints_map=constraints_map, use_docker=use_docker,
    )
    display_implementation_result(success)
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
