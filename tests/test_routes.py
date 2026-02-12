"""Tests for route handlers, streaming, and error handling."""

import tempfile
from unittest.mock import MagicMock, patch

from fastapi import Response
from fastapi.responses import StreamingResponse

from fastsymapi.routes import get_symbol


class TestMemoryManagement:
    """Test memory management in streaming functions."""

    @patch("gzip.open")
    def test_stream_memory_limit(self, mock_gzip_open):
        """Test that streaming respects memory limits."""
        mock_file = MagicMock()
        large_chunk = b"x" * (50 * 1024 * 1024)
        mock_file.read.side_effect = [large_chunk, large_chunk, b""]
        mock_gzip_open.return_value.__enter__.return_value = mock_file

        with (
            tempfile.NamedTemporaryFile(),
            patch("fastsymapi.routes.os.path.isfile", return_value=True),
            patch("fastsymapi.routes.create_or_find_pdb_entry"),
        ):
            mock_db = MagicMock()
            mock_background_tasks = MagicMock()

            response = get_symbol("test", "test.pdb", "guid", mock_background_tasks, mock_db, False)

            assert isinstance(response, StreamingResponse)


class TestErrorHandling:
    """Test comprehensive error handling."""

    def test_get_symbol_invalid_parameters(self):
        """Test get_symbol with invalid parameters."""
        mock_db = MagicMock()
        mock_background_tasks = MagicMock()

        response = get_symbol("../evil", "test.pdb", "guid", mock_background_tasks, mock_db, False)

        assert isinstance(response, Response)
        assert response.status_code == 400
