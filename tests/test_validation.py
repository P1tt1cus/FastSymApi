"""Tests for input validation and path sanitization."""

import pytest

from fastsymapi.validation import sanitize_path_component, validate_pdb_entry_fields


class TestPathSanitization:
    """Test path sanitization functions."""

    def test_sanitize_valid_path_component(self):
        """Test that valid path components pass through unchanged."""
        valid_components = ["test.pdb", "valid_file", "normal-file", "file123"]
        for component in valid_components:
            assert sanitize_path_component(component) == component

    def test_sanitize_prevents_directory_traversal(self):
        """Test that directory traversal attempts are blocked."""
        with pytest.raises(ValueError):
            sanitize_path_component("../evil")

        with pytest.raises(ValueError):
            sanitize_path_component("..\\evil")

        with pytest.raises(ValueError):
            sanitize_path_component("normal/../traversal")

    def test_sanitize_prevents_path_separators(self):
        """Test that path separators are blocked."""
        with pytest.raises(ValueError):
            sanitize_path_component("path/with/slashes")

        with pytest.raises(ValueError):
            sanitize_path_component("path\\with\\backslashes")

    def test_sanitize_prevents_invalid_characters(self):
        """Test that invalid characters are blocked."""
        with pytest.raises(ValueError):
            sanitize_path_component("file<with>invalid")

        with pytest.raises(ValueError):
            sanitize_path_component("file|with|pipes")

        with pytest.raises(ValueError):
            sanitize_path_component("file*with*wildcards")

    def test_sanitize_empty_component(self):
        """Test that empty components are rejected."""
        with pytest.raises(ValueError):
            sanitize_path_component("")

        with pytest.raises(ValueError):
            sanitize_path_component(None)


class TestInputValidation:
    """Test input validation functions."""

    def test_validate_pdb_entry_fields_valid(self):
        """Test validation with valid inputs."""
        validate_pdb_entry_fields("test.pdb", "guid123", "file.pdb")

    def test_validate_pdb_entry_fields_empty(self):
        """Test validation rejects empty fields."""
        with pytest.raises(ValueError):
            validate_pdb_entry_fields("", "guid", "file")

        with pytest.raises(ValueError):
            validate_pdb_entry_fields("name", "", "file")

        with pytest.raises(ValueError):
            validate_pdb_entry_fields("name", "guid", "")

    def test_validate_pdb_entry_fields_too_long(self):
        """Test validation rejects fields that are too long."""
        long_string = "a" * 256

        with pytest.raises(ValueError):
            validate_pdb_entry_fields(long_string, "guid", "file")

        with pytest.raises(ValueError):
            validate_pdb_entry_fields("name", long_string, "file")

        with pytest.raises(ValueError):
            validate_pdb_entry_fields("name", "guid", long_string)

    def test_validate_pdb_entry_fields_invalid_characters(self):
        """Test validation rejects invalid characters."""
        with pytest.raises(ValueError):
            validate_pdb_entry_fields("../evil", "guid", "file")

        with pytest.raises(ValueError):
            validate_pdb_entry_fields("name", "guid|invalid", "file")
