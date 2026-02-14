from pathlib import Path

import yaml
import pytest

from orchestrator.constraint_checks import check_constraints
from orchestrator.models import ConstraintSet, TaskConstraints


@pytest.fixture(scope="module")
def orchestrator_constraints():
    """Load orchestrator constraints from YAML for self-testing.

    Returns:
        TaskConstraints loaded from constraints/orchestrator.yaml.
    """
    constraints_path = Path(__file__).parent.parent / "constraints" / "orchestrator.yaml"
    with open(constraints_path) as f:
        data = yaml.safe_load(f)
    return TaskConstraints(
        primary=ConstraintSet(**data.get("primary", {})),
        secondary=ConstraintSet(**data.get("secondary", {})),
        target_files=data.get("target_files", []),
    )


@pytest.fixture(scope="module")
def project_root():
    """Provide the project root directory path.

    Returns:
        Path to the project root.
    """
    return Path(__file__).parent.parent


def _get_target_files():
    """Read target files from orchestrator constraints YAML.

    Returns:
        List of target file paths from the constraints config.
    """
    constraints_path = Path(__file__).parent.parent / "constraints" / "orchestrator.yaml"
    with open(constraints_path) as f:
        data = yaml.safe_load(f)
    return data.get("target_files", [])


@pytest.mark.parametrize("target_file", _get_target_files())
class TestSelfConstraints:
    """Tests that orchestrator source files meet their own constraints."""

    def test_orchestrator_meets_primary_constraints(
        self, target_file, orchestrator_constraints, project_root
    ):
        """Test that the target file meets primary constraints.

        Args:
            target_file: Path to the source file being checked.
            orchestrator_constraints: Loaded TaskConstraints.
            project_root: Path to the project root.
        """
        source_path = project_root / target_file
        if not source_path.exists():
            pytest.skip(f"{target_file} not yet implemented")
        source_code = source_path.read_text()
        primary_result, _ = check_constraints(source_code, orchestrator_constraints)
        assert primary_result.passed, (
            f"{target_file} violates primary constraints: {primary_result.violations}"
        )

    def test_orchestrator_meets_secondary_constraints(
        self, target_file, orchestrator_constraints, project_root
    ):
        """Test that the target file meets secondary constraints.

        Args:
            target_file: Path to the source file being checked.
            orchestrator_constraints: Loaded TaskConstraints.
            project_root: Path to the project root.
        """
        source_path = project_root / target_file
        if not source_path.exists():
            pytest.skip(f"{target_file} not yet implemented")
        source_code = source_path.read_text()
        _, secondary_result = check_constraints(source_code, orchestrator_constraints)
        assert secondary_result.passed, (
            f"{target_file} violates secondary constraints: {secondary_result.violations}"
        )
