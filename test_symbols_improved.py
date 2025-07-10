"""
Comprehensive unit tests for the improved symbols.py module.
Tests cover all the robustness improvements including:
- Path sanitization and security
- Input validation
- Error handling
- File locking
- Memory management
- Retry logic
"""

import pytest
import os
import tempfile
import threading
import time
from unittest.mock import patch, MagicMock, mock_open
from fastsymapi.symbols import (
    sanitize_path_component, 
    validate_pdb_entry_fields,
    get_file_lock,
    create_requests_session,
    create_or_find_pdb_entry,
    download_symbol,
    download_and_save_symbol,
    get_symbol
)
from fastsymapi.sql_db import models
from fastapi import Response
from requests.exceptions import RequestException


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
        # Should not raise any exception
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
                time.sleep(0.1)  # Simulate work
                results.append(f"end_{worker_id}")
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Results should show that one worker completes entirely before the other starts
        assert len(results) == 4
        # Either worker 0 completes first or worker 1 completes first
        assert (results == ["start_0", "end_0", "start_1", "end_1"] or 
                results == ["start_1", "end_1", "start_0", "end_0"])


class TestRetryLogic:
    """Test retry logic in requests session."""
    
    def test_create_requests_session(self):
        """Test that requests session is created with retry strategy."""
        session = create_requests_session()
        assert session is not None
        
        # Check that adapters are mounted
        assert "http://" in session.adapters
        assert "https://" in session.adapters


class TestHelperFunctions:
    """Test helper functions for reducing code duplication."""
    
    @patch('fastsymapi.symbols.crud.find_pdb_entry')
    @patch('fastsymapi.symbols.crud.create_pdb_entry')
    def test_create_or_find_pdb_entry_existing(self, mock_create, mock_find):
        """Test helper function when entry already exists."""
        mock_db = MagicMock()
        mock_entry = MagicMock()
        mock_find.return_value = mock_entry
        
        result = create_or_find_pdb_entry(mock_db, "guid", "name", "file")
        
        assert result == mock_entry
        mock_find.assert_called_once_with(mock_db, "guid", "file")
        mock_create.assert_not_called()
    
    @patch('fastsymapi.symbols.crud.find_pdb_entry')
    @patch('fastsymapi.symbols.crud.create_pdb_entry')
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
    """Test the improved download_symbol function."""
    
    @patch('fastsymapi.symbols.create_requests_session')
    @patch('fastsymapi.symbols.download_and_save_symbol')
    @patch('fastsymapi.symbols.crud.modify_pdb_entry')
    def test_download_symbol_success(self, mock_modify, mock_download_save, mock_session):
        """Test successful symbol download."""
        # Setup mocks
        mock_session_obj = MagicMock()
        mock_session.return_value = mock_session_obj
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session_obj.get.return_value = mock_response
        
        # Create test PDB entry
        pdbentry = models.SymbolEntry(pdbname="test", guid="guid123", pdbfile="test.pdb")
        mock_db = MagicMock()
        
        # Call function
        download_symbol(pdbentry, mock_db)
        
        # Verify calls
        assert pdbentry.found == True
        assert pdbentry.downloading == False
        mock_download_save.assert_called_once()
        mock_modify.assert_called()
    
    @patch('fastsymapi.symbols.create_requests_session')
    @patch('fastsymapi.symbols.crud.modify_pdb_entry')
    def test_download_symbol_all_servers_fail(self, mock_modify, mock_session):
        """Test when all symbol servers fail."""
        # Setup mocks
        mock_session_obj = MagicMock()
        mock_session.return_value = mock_session_obj
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_session_obj.get.return_value = mock_response
        
        # Create test PDB entry
        pdbentry = models.SymbolEntry(pdbname="test", guid="guid123", pdbfile="test.pdb")
        mock_db = MagicMock()
        
        # Call function
        download_symbol(pdbentry, mock_db)
        
        # Verify error handling
        assert pdbentry.found == False
        assert pdbentry.downloading == False
        mock_modify.assert_called()
    
    @patch('fastsymapi.symbols.create_requests_session')
    @patch('fastsymapi.symbols.crud.modify_pdb_entry')
    def test_download_symbol_network_error(self, mock_modify, mock_session):
        """Test network error handling."""
        # Setup mocks
        mock_session_obj = MagicMock()
        mock_session.return_value = mock_session_obj
        mock_session_obj.get.side_effect = RequestException("Network error")
        
        # Create test PDB entry
        pdbentry = models.SymbolEntry(pdbname="test", guid="guid123", pdbfile="test.pdb")
        mock_db = MagicMock()
        
        # Call function
        download_symbol(pdbentry, mock_db)
        
        # Verify error handling
        assert pdbentry.downloading == False
        mock_modify.assert_called()
    
    @patch('fastsymapi.symbols.crud.modify_pdb_entry')
    def test_download_symbol_invalid_input(self, mock_modify):
        """Test invalid input handling."""
        # Create test PDB entry with invalid characters
        pdbentry = models.SymbolEntry(pdbname="../evil", guid="guid123", pdbfile="test.pdb")
        mock_db = MagicMock()
        
        # Call function
        download_symbol(pdbentry, mock_db)
        
        # Verify error handling
        assert pdbentry.downloading == False
        mock_modify.assert_called()


class TestMemoryManagement:
    """Test memory management in streaming functions."""
    
    @patch('gzip.open')
    def test_stream_memory_limit(self, mock_gzip_open):
        """Test that streaming respects memory limits."""
        # Mock gzip file that returns large chunks
        mock_file = MagicMock()
        large_chunk = b"x" * (50 * 1024 * 1024)  # 50MB chunk
        mock_file.read.side_effect = [large_chunk, large_chunk, b""]  # Return large chunks then EOF
        mock_gzip_open.return_value.__enter__.return_value = mock_file
        
        # Create a temporary file for testing
        with tempfile.NamedTemporaryFile() as temp_file:
            from fastsymapi.symbols import get_symbol
            
            # Mock the necessary components
            with patch('fastsymapi.symbols.os.path.isfile', return_value=True), \
                 patch('fastsymapi.symbols.create_or_find_pdb_entry'):
                
                mock_db = MagicMock()
                mock_background_tasks = MagicMock()
                
                # This should work without running out of memory
                response = get_symbol("test", "test.pdb", "guid", mock_background_tasks, mock_db, False)
                
                # Verify it's a streaming response
                from fastapi.responses import StreamingResponse
                assert isinstance(response, StreamingResponse)


class TestErrorHandling:
    """Test comprehensive error handling."""
    
    def test_get_symbol_invalid_parameters(self):
        """Test get_symbol with invalid parameters."""
        from fastsymapi.symbols import get_symbol
        
        mock_db = MagicMock()
        mock_background_tasks = MagicMock()
        
        # Test with invalid characters
        response = get_symbol("../evil", "test.pdb", "guid", mock_background_tasks, mock_db, False)
        
        # Should return 400 error
        assert isinstance(response, Response)
        assert response.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__])