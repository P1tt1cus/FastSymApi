"""Symbol download and file management logic.

Single Responsibility: This module handles downloading symbols from
remote servers and saving them to disk, including file locking,
HTTP session management, and gzip handling.

Open/Closed: The SYM_URLS list in config allows adding new symbol
servers without modifying this module's download logic.
"""

import contextlib
import gzip
import os
import shutil
import threading
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy.orm import Session
from urllib3.util.retry import Retry

from fastsymapi.config import (
    CHUNK_SIZE,
    MAX_MEMORY_USAGE,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_FACTOR,
    SYM_URLS,
    SYMBOL_PATH,
)
from fastsymapi.logging import logger
from fastsymapi.sql_db import crud, models
from fastsymapi.validation import sanitize_path_component, validate_pdb_entry_fields

_download_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def get_file_lock(file_path: str) -> threading.Lock:
    """Get or create a lock for a specific file path."""
    with _locks_lock:
        if file_path not in _download_locks:
            _download_locks[file_path] = threading.Lock()
        return _download_locks[file_path]


def create_requests_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()

    retry_strategy = Retry(
        total=MAX_RETRY_ATTEMPTS,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        backoff_factor=RETRY_BACKOFF_FACTOR,
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


def create_or_find_pdb_entry(
    db: Session, guid: str, pdbname: str, pdbfile: str, found: bool = False
) -> models.SymbolEntry:
    """Find an existing PDB entry or create a new one."""
    validate_pdb_entry_fields(pdbname, guid, pdbfile)

    pdbentry = crud.find_pdb_entry(db, guid, pdbfile)
    if not pdbentry:
        pdbentry = crud.create_pdb_entry(db, guid, pdbname, pdbfile, found)
    return pdbentry


def get_pdb_size(resp: requests.Response) -> int | None:
    """Extract the content length from the response headers."""
    for header in ["Content-Length", "x-goog-stored-content-length"]:
        if resp.headers.get(header):
            return int(resp.headers[header])

    logger.error(f"Could not get content length from server: {resp.status_code}")
    return None


def download_and_save_symbol(pdbentry: models.SymbolEntry, resp: requests.Response, db: Session) -> None:
    """Download a symbol file and save it to disk with gzip compression."""
    logger.warning(f"Downloading... {pdbentry.guid} {pdbentry.pdbfile}")

    pdb_file_path = os.path.join(
        SYMBOL_PATH,
        sanitize_path_component(pdbentry.pdbname),
        sanitize_path_component(pdbentry.guid),
    )

    file_lock = get_file_lock(pdb_file_path)
    pdb_tmp_file_path = os.path.join(pdb_file_path, f"tmp_{sanitize_path_component(pdbentry.pdbfile)}.gzip")

    with file_lock:
        try:
            if not os.path.exists(pdb_file_path):
                os.makedirs(pdb_file_path, mode=0o755)

            content_encoding = resp.headers.get("Content-Encoding", "")
            is_gzip_supported = "gzip" in content_encoding.lower()

            pdbfile_handle = open(pdb_tmp_file_path, "wb") if is_gzip_supported else gzip.open(pdb_tmp_file_path, "wb")

            pdb_size = get_pdb_size(resp)
            if pdb_size is None:
                pdbentry.downloading = False
                crud.modify_pdb_entry(db, pdbentry)
                pdbfile_handle.close()
                if os.path.exists(pdb_tmp_file_path):
                    os.remove(pdb_tmp_file_path)
                return

            _stream_download(pdbfile_handle, resp, pdb_size, pdbentry)
            pdbfile_handle.close()

            logger.info(f"Successfully downloaded... {pdbentry.guid} {pdbentry.pdbfile}")

            final_pdb_file_path = os.path.join(pdb_file_path, f"{sanitize_path_component(pdbentry.pdbfile)}.gzip")
            shutil.move(pdb_tmp_file_path, final_pdb_file_path)

        except Exception as e:
            logger.error(f"Error downloading symbol {pdbentry.guid}/{pdbentry.pdbfile}: {e}")
            pdbentry.downloading = False
            crud.modify_pdb_entry(db, pdbentry)
            if os.path.exists(pdb_tmp_file_path):
                with contextlib.suppress(OSError):
                    os.remove(pdb_tmp_file_path)
            raise


def _stream_download(pdbfile_handle, resp: requests.Response, pdb_size: int, pdbentry: models.SymbolEntry) -> None:
    """Stream download content to a file handle with progress logging."""
    downloaded = 0
    last_logged_percent = -1
    chunks_in_memory = 0

    while downloaded < pdb_size:
        remaining = pdb_size - downloaded
        chunk_size = min(CHUNK_SIZE, remaining)
        chunk = resp.raw.read(chunk_size)

        if not chunk:
            break

        pdbfile_handle.write(chunk)
        downloaded += len(chunk)
        chunks_in_memory += 1

        if chunks_in_memory * CHUNK_SIZE > MAX_MEMORY_USAGE:
            pdbfile_handle.flush()
            chunks_in_memory = 0

        percent = int((downloaded / pdb_size) * 100)
        if percent // 5 > last_logged_percent:
            last_logged_percent = percent // 5
            logger.warning(f"Downloading... {pdbentry.guid} {pdbentry.pdbfile} {percent}%")


def download_symbol(pdbentry: models.SymbolEntry, db: Session) -> None:
    """Iterate over symbol servers looking for the requested PDB file."""
    try:
        validate_pdb_entry_fields(pdbentry.pdbname, pdbentry.guid, pdbentry.pdbfile)
    except ValueError as e:
        logger.error(f"Invalid PDB entry fields: {e}")
        pdbentry.downloading = False
        crud.modify_pdb_entry(db, pdbentry)
        return

    session = create_requests_session()
    found = False

    for sym_url in SYM_URLS:
        try:
            symbol_url = f"{sym_url}/{quote(pdbentry.pdbname)}/{quote(pdbentry.guid)}/{quote(pdbentry.pdbfile)}"

            logger.debug(f"Trying to download from: {symbol_url}")
            resp = session.get(symbol_url, stream=True, timeout=30)

            if resp.status_code == 200:
                pdbentry.found = True
                download_and_save_symbol(pdbentry, resp, db)
                found = True
                break
            else:
                logger.debug(f"Could not find symbol: {symbol_url} {resp.status_code}")

        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error while downloading from {sym_url}: {e}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error while downloading from {sym_url}: {e}")
            continue

    if not found:
        logger.error(
            f"Failed to download symbol {pdbentry.pdbname}/{pdbentry.guid}/{pdbentry.pdbfile} "
            f"from all available servers"
        )
        pdbentry.found = False

    pdbentry.downloading = False
    crud.modify_pdb_entry(db, pdbentry)
