"""Load and resolve constraint profiles for task and function scopes."""

from pathlib import Path

import yaml

from orchestrator.models import ConstraintSet, ParsedSpec, TaskConstraints


def load_profiles(profiles_path: Path) -> dict:
    """Load a profile YAML file into a flattened dictionary.

    Args:
        profiles_path: Path to the constraint profiles YAML file.

    Returns:
        Flattened dictionary where profile names are top-level keys and
        function overrides are stored under the ``functions`` key.
    """
    data = yaml.safe_load(profiles_path.read_text())
    if not data:
        raise ValueError("Profiles file is empty")

    profiles = dict(data.get("profiles", {}))
    profiles["functions"] = data.get("functions", {})
    return profiles


def resolve_constraints(
    spec: ParsedSpec, profiles: dict, function_name: str | None = None
) -> TaskConstraints:
    """Resolve task constraints from a spec and loaded profiles.

    Args:
        spec: Parsed task specification.
        profiles: Flattened profile dictionary from ``load_profiles``.
        function_name: Optional function name for function-level resolution.

    Returns:
        Resolved TaskConstraints for the task or selected function.
    """
    profile_name = _select_profile_name(spec, function_name)
    profile_data = profiles.get(profile_name)
    if profile_data is None:
        raise ValueError(f"Unknown constraint profile: {profile_name}")

    base_constraints = TaskConstraints(
        primary=ConstraintSet(**profile_data.get("primary", {})),
        secondary=ConstraintSet(**profile_data.get("secondary", {})),
        target_files=list(spec.target_files),
        guidance=list(profile_data.get("guidance") or []),
    )

    resolved_function = function_name or spec.name
    function_overrides = profiles.get("functions", {}).get(resolved_function)
    if not function_overrides:
        return base_constraints
    return _merge_function_overrides(base_constraints, function_overrides)


def _select_profile_name(spec: ParsedSpec, function_name: str | None) -> str:
    """Choose the profile name for the requested resolution scope.

    Args:
        spec: Parsed task specification.
        function_name: Optional function name for function-level resolution.

    Returns:
        Profile name selected from function-level or task-level settings.
    """
    if function_name is None:
        return spec.constraint_profile

    for function_spec in spec.functions:
        if function_spec.name == function_name and function_spec.constraint_profile:
            return function_spec.constraint_profile
    return spec.constraint_profile


def _merge_function_overrides(
    constraints: TaskConstraints, overrides: dict
) -> TaskConstraints:
    """Merge function-level profile overrides onto base task constraints.

    Args:
        constraints: Base task constraints produced from a profile.
        overrides: Function-specific override dictionary.

    Returns:
        New TaskConstraints with function overrides applied.
    """
    primary_data = constraints.primary.model_dump()
    primary_data.update(overrides.get("primary", {}))

    secondary_data = constraints.secondary.model_dump()
    secondary_data.update(overrides.get("secondary", {}))

    guidance = list(constraints.guidance)
    if "guidance" in overrides:
        guidance = list(overrides.get("guidance") or [])

    return TaskConstraints(
        primary=ConstraintSet(**primary_data),
        secondary=ConstraintSet(**secondary_data),
        target_files=list(constraints.target_files),
        guidance=guidance,
    )
