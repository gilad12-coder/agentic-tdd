"""Parse YAML spec files into ParsedSpec models."""

from pathlib import Path

import yaml

from orchestrator.models import ParsedSpec


def parse_spec(spec_path: Path) -> ParsedSpec:
    """Parse a YAML spec file and return a ParsedSpec model.

    Args:
        spec_path: Path to the YAML spec file.

    Returns:
        ParsedSpec populated from the YAML data.
    """
    data = yaml.safe_load(spec_path.read_text())
    if not data:
        raise ValueError("Spec file is empty")
    return ParsedSpec(**data)
