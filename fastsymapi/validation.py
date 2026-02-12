"""Input validation and path sanitization.

Single Responsibility: This module handles all input validation
and path sanitization logic to prevent directory traversal and
injection attacks.
"""

import re


def sanitize_path_component(component: str) -> str:
    """Sanitize a path component to prevent directory traversal attacks."""
    if not component:
        raise ValueError("Path component cannot be empty")

    if ".." in component or "/" in component or "\\" in component:
        raise ValueError(f"Path traversal or separator characters not allowed: {component}")

    if not re.match(r"^[a-zA-Z0-9._-]+$", component):
        raise ValueError(f"Invalid characters in path component: {component}")

    return component


def validate_pdb_entry_fields(pdbname: str, guid: str, pdbfile: str) -> None:
    """Validate PDB entry fields to prevent injection attacks."""
    if not pdbname or len(pdbname) > 255:
        raise ValueError("Invalid pdbname: must be non-empty and <= 255 characters")

    if not guid or len(guid) > 255:
        raise ValueError("Invalid guid: must be non-empty and <= 255 characters")

    if not pdbfile or len(pdbfile) > 255:
        raise ValueError("Invalid pdbfile: must be non-empty and <= 255 characters")

    sanitize_path_component(pdbname)
    sanitize_path_component(guid)
    sanitize_path_component(pdbfile)
