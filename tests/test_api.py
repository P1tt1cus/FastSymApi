"""API-level integration tests for FastSymApi."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fastsymapi import app
from fastsymapi.download import download_symbol
from fastsymapi.sql_db import models

client = TestClient(app)


@pytest.fixture
def mock_gzip_open():
    return MagicMock()


def test_fail_get_symbol_api():
    """Test a failed symbol retrieval."""
    response = client.get("/download/symbols/notreal/notreal/pdbfile")
    assert response.status_code == 404


def test_health_check():
    """Test the health check endpoint returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("gzip.open")
@patch("fastsymapi.download.requests.get")
@patch("fastsymapi.download.crud.modify_pdb_entry")
@patch("fastsymapi.download.crud.create_pdb_entry")
@patch("fastsymapi.download.os.path.exists")
@patch("fastsymapi.download.os.makedirs")
@patch("fastsymapi.download.open", new_callable=MagicMock)
@patch("fastsymapi.download.shutil.move")
def test_successful_pdb_download(
    mock_move,
    mock_open,
    mock_makedirs,
    mock_exists,
    mock_create_pdb_entry,
    mock_modify_pdb_entry,
    mock_get,
    mock_gzip_open,
):
    # Arrange
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response
    mock_exists.return_value = False
    mock_open.return_value.__enter__.return_value = MagicMock()
    mock_gzip_open.return_value.__enter__.return_value = MagicMock()
    pdbentry = models.SymbolEntry(pdbname="test", guid="test", pdbfile="test")
    db = MagicMock()

    # Act
    download_symbol(pdbentry, db)
