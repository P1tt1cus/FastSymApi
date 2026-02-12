"""Tests for symbol download logic, file locking, and HTTP session management."""

import threading
import time
from unittest.mock import MagicMock, patch

from requests.exceptions import RequestException

from fastsymapi.download import (
    create_or_find_pdb_entry,
    create_requests_session,
    download_symbol,
    get_file_lock,
)
from fastsymapi.sql_db import models


class TestFileLocking:
    """Test file locking mechanisms."""

    def test_get_file_lock_same_path(self):
        """Test that the same path returns the same lock."""
        lock1 = get_file_lock("/test/path")
        lock2 = get_file_lock("/test/path")
        assert lock1 is lock2

    def test_get_file_lock_different_paths(self):
        """Test that different paths return different locks."""
        lock1 = get_file_lock("/test/path1")
        lock2 = get_file_lock("/test/path2")
        assert lock1 is not lock2

    def test_file_lock_concurrency(self):
        """Test that file locks prevent concurrent access."""
        results = []

        def worker(worker_id):
            lock = get_file_lock("/test/concurrent")
            with lock:
                results.append(f"start_{worker_id}")
                time.sleep(0.1)
                results.append(f"end_{worker_id}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 4
        assert results == ["start_0", "end_0", "start_1", "end_1"] or results == [
            "start_1",
            "end_1",
            "start_0",
            "end_0",
        ]


class TestRetryLogic:
    """Test retry logic in requests session."""

    def test_create_requests_session(self):
        """Test that requests session is created with retry strategy."""
        session = create_requests_session()
        assert session is not None
        assert "http://" in session.adapters
        assert "https://" in session.adapters


class TestHelperFunctions:
    """Test helper functions for reducing code duplication."""

    @patch("fastsymapi.download.crud.find_pdb_entry")
    @patch("fastsymapi.download.crud.create_pdb_entry")
    def test_create_or_find_pdb_entry_existing(self, mock_create, mock_find):
        """Test helper function when entry already exists."""
        mock_db = MagicMock()
        mock_entry = MagicMock()
        mock_find.return_value = mock_entry

        result = create_or_find_pdb_entry(mock_db, "guid", "name", "file")

        assert result == mock_entry
        mock_find.assert_called_once_with(mock_db, "guid", "file")
        mock_create.assert_not_called()

    @patch("fastsymapi.download.crud.find_pdb_entry")
    @patch("fastsymapi.download.crud.create_pdb_entry")
    def test_create_or_find_pdb_entry_new(self, mock_create, mock_find):
        """Test helper function when entry doesn't exist."""
        mock_db = MagicMock()
        mock_entry = MagicMock()
        mock_find.return_value = None
        mock_create.return_value = mock_entry

        result = create_or_find_pdb_entry(mock_db, "guid", "name", "file", True)

        assert result == mock_entry
        mock_find.assert_called_once_with(mock_db, "guid", "file")
        mock_create.assert_called_once_with(mock_db, "guid", "name", "file", True)


class TestDownloadSymbol:
    """Test the download_symbol function."""

    @patch("fastsymapi.download.create_requests_session")
    @patch("fastsymapi.download.download_and_save_symbol")
    @patch("fastsymapi.download.crud.modify_pdb_entry")
    def test_download_symbol_success(self, mock_modify, mock_download_save, mock_session):
        """Test successful symbol download."""
        mock_session_obj = MagicMock()
        mock_session.return_value = mock_session_obj
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session_obj.get.return_value = mock_response

        pdbentry = models.SymbolEntry(pdbname="test", guid="guid123", pdbfile="test.pdb")
        mock_db = MagicMock()

        download_symbol(pdbentry, mock_db)

        assert pdbentry.found is True
        assert pdbentry.downloading is False
        mock_download_save.assert_called_once()
        mock_modify.assert_called()

    @patch("fastsymapi.download.create_requests_session")
    @patch("fastsymapi.download.crud.modify_pdb_entry")
    def test_download_symbol_all_servers_fail(self, mock_modify, mock_session):
        """Test when all symbol servers fail."""
        mock_session_obj = MagicMock()
        mock_session.return_value = mock_session_obj
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_session_obj.get.return_value = mock_response

        pdbentry = models.SymbolEntry(pdbname="test", guid="guid123", pdbfile="test.pdb")
        mock_db = MagicMock()

        download_symbol(pdbentry, mock_db)

        assert pdbentry.found is False
        assert pdbentry.downloading is False
        mock_modify.assert_called()

    @patch("fastsymapi.download.create_requests_session")
    @patch("fastsymapi.download.crud.modify_pdb_entry")
    def test_download_symbol_network_error(self, mock_modify, mock_session):
        """Test network error handling."""
        mock_session_obj = MagicMock()
        mock_session.return_value = mock_session_obj
        mock_session_obj.get.side_effect = RequestException("Network error")

        pdbentry = models.SymbolEntry(pdbname="test", guid="guid123", pdbfile="test.pdb")
        mock_db = MagicMock()

        download_symbol(pdbentry, mock_db)

        assert pdbentry.downloading is False
        mock_modify.assert_called()

    @patch("fastsymapi.download.crud.modify_pdb_entry")
    def test_download_symbol_invalid_input(self, mock_modify):
        """Test invalid input handling."""
        pdbentry = models.SymbolEntry(pdbname="../evil", guid="guid123", pdbfile="test.pdb")
        mock_db = MagicMock()

        download_symbol(pdbentry, mock_db)

        assert pdbentry.downloading is False
        mock_modify.assert_called()
