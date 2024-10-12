from fastsymapi.symbols import download_symbol
from fastsymapi.sql_db import models
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastsymapi import app
import pytest

client = TestClient(app)


@pytest.fixture
def mock_gzip_open():
    return MagicMock()


def test_fail_get_symbol_api():
    """Test a failed symbol retrieval"""

    response = client.get("/download/symbols/notreal/notreal/pdbfile")

    assert response.status_code == 404  # or whatever status code you expect


@patch("gzip.open")
@patch("fastsymapi.symbols.requests.get")
@patch("fastsymapi.symbols.crud.modify_pdb_entry")
@patch("fastsymapi.symbols.crud.create_pdb_entry")
@patch("fastsymapi.symbols.os.path.exists")
@patch("fastsymapi.symbols.os.makedirs")
@patch("fastsymapi.symbols.open", new_callable=MagicMock)
@patch("fastsymapi.symbols.shutil.move")
def test_successful_pdb_download(
    self,
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
