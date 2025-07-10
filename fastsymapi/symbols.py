from fastapi import APIRouter, Depends, Response, BackgroundTasks, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder
from fastsymapi.sql_db.database import get_db, session_local
from fastsymapi.sql_db import crud, models
from fastsymapi.logging import logger
import requests
import click
from sqlalchemy.orm import Session
import os
import shutil
import gzip
import threading
import time
import re
from urllib.parse import quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sym = APIRouter()

# Make CHUNK_SIZE configurable via environment variable
CHUNK_SIZE = int(os.environ.get('FASTSYM_CHUNK_SIZE', 1024*1024*2))
MAX_RETRY_ATTEMPTS = int(os.environ.get('FASTSYM_MAX_RETRIES', 3))
RETRY_BACKOFF_FACTOR = float(os.environ.get('FASTSYM_RETRY_BACKOFF', 0.3))
MAX_MEMORY_USAGE = int(os.environ.get('FASTSYM_MAX_MEMORY_MB', 100)) * 1024 * 1024

SYMBOL_PATH = os.path.join(os.path.dirname(__file__), "symbols")

# File lock for concurrent downloads
_download_locks = {}
_locks_lock = threading.Lock()

SYM_URLS = [
    "http://msdl.microsoft.com/download/symbols",
    "http://chromium-browser-symsrv.commondatastorage.googleapis.com",
    "http://symbols.mozilla.org",
    "http://symbols.mozilla.org/try"
]


def sanitize_path_component(component: str) -> str:
    """Sanitize a path component to prevent directory traversal attacks."""
    if not component:
        raise ValueError("Path component cannot be empty")
    
    # Remove any path traversal sequences and path separators
    if '..' in component or '/' in component or '\\' in component:
        raise ValueError(f"Path traversal or separator characters not allowed: {component}")
    
    # Only allow alphanumeric characters, hyphens, underscores, and dots
    if not re.match(r'^[a-zA-Z0-9._-]+$', component):
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
    
    # Sanitize each component
    sanitize_path_component(pdbname)
    sanitize_path_component(guid) 
    sanitize_path_component(pdbfile)


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
        allowed_methods=["HEAD", "GET", "OPTIONS"],  # Updated parameter name
        backoff_factor=RETRY_BACKOFF_FACTOR
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


def create_or_find_pdb_entry(db: Session, guid: str, pdbname: str, pdbfile: str, found: bool = False) -> models.SymbolEntry:
    """Helper function to create or find a PDB entry, reducing code duplication."""
    validate_pdb_entry_fields(pdbname, guid, pdbfile)
    
    pdbentry = crud.find_pdb_entry(db, guid, pdbfile)
    if not pdbentry:
        pdbentry = crud.create_pdb_entry(db, guid, pdbname, pdbfile, found)
    return pdbentry


def download_symbol(pdbentry: models.SymbolEntry, db: Session) -> None:
    """ Iterate over SYM_URLs looking for the requested PDB file """
    
    # Validate PDB entry fields
    try:
        validate_pdb_entry_fields(pdbentry.pdbname, pdbentry.guid, pdbentry.pdbfile)
    except ValueError as e:
        logger.error(f"Invalid PDB entry fields: {e}")
        pdbentry.downloading = False
        crud.modify_pdb_entry(db, pdbentry)
        return

    session = create_requests_session()
    found = False
    
    # Iterate over the symbol server URLs
    for sym_url in SYM_URLS:
        try:
            # Check if symbol exists on the server
            symbol_url = sym_url + \
                f"/{quote(pdbentry.pdbname)}/{quote(pdbentry.guid)}/{quote(pdbentry.pdbfile)}"
            
            logger.debug(f"Trying to download from: {symbol_url}")
            resp = session.get(symbol_url, stream=True, timeout=30)

            # If the symbol was found download it
            if resp.status_code == 200:
                pdbentry.found = True
                download_and_save_symbol(pdbentry, resp, db)
                found = True
                break

            # Unable to find PDB at this Symbol Server
            else:
                logger.debug(f"Could not find symbol: {symbol_url} {resp.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error while downloading from {sym_url}: {e}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error while downloading from {sym_url}: {e}")
            continue

    # If no symbol server had the file, log an explicit error
    if not found:
        logger.error(f"Failed to download symbol {pdbentry.pdbname}/{pdbentry.guid}/{pdbentry.pdbfile} from all available servers")
        pdbentry.found = False

    # Set the PDB entry to 'finished' downloading
    pdbentry.downloading = False
    crud.modify_pdb_entry(db, pdbentry)


def download_and_save_symbol(pdbentry, resp, db):
    """ Download the symbol and save it to disk """

    # Notify that the download is beginning
    logger.warning(f"Downloading... {pdbentry.guid} {pdbentry.pdbfile}")

    # Create the PDB directory with GUID if it does not exist
    pdb_file_path = os.path.join(SYMBOL_PATH, 
                                sanitize_path_component(pdbentry.pdbname), 
                                sanitize_path_component(pdbentry.guid))
    
    # Get file lock to prevent race conditions
    file_lock = get_file_lock(pdb_file_path)
    
    with file_lock:
        try:
            if not os.path.exists(pdb_file_path):
                os.makedirs(pdb_file_path, mode=0o755)

            # Logic that identifies whether its a gzip or not
            content_encoding = resp.headers.get("Content-Encoding", "")
            is_gzip_supported = "gzip" in content_encoding.lower()

            # Create the PDB file and iterate over it writing the chunks
            pdb_tmp_file_path = os.path.join(
                pdb_file_path, f"tmp_{sanitize_path_component(pdbentry.pdbfile)}.gzip")

            # if the file is already compressed, just write the raw bytes
            if is_gzip_supported:
                pdbfile_handle = open(pdb_tmp_file_path, 'wb')
            # else, we must compress it ourselves
            else:
                pdbfile_handle = gzip.open(pdb_tmp_file_path, 'wb')

            # Get the size of the PDB buffer being downloaded
            pdb_size = get_pdb_size(resp)
            if pdb_size is None:
                pdbentry.downloading = False
                crud.modify_pdb_entry(db, pdbentry)
                if pdbfile_handle:
                    pdbfile_handle.close()
                if os.path.exists(pdb_tmp_file_path):
                    os.remove(pdb_tmp_file_path)
                return

            # Download with memory usage monitoring
            downloaded = 0
            percent = 0
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
                
                # Monitor memory usage
                if chunks_in_memory * CHUNK_SIZE > MAX_MEMORY_USAGE:
                    pdbfile_handle.flush()
                    chunks_in_memory = 0
                
                percent = int((downloaded / pdb_size) * 100)
                if percent // 5 > last_logged_percent:  # Log every 5%
                    last_logged_percent = percent // 5
                    logger.warning(f"Downloading... {pdbentry.guid} {pdbentry.pdbfile} {percent}%")

            # Close the file handle
            pdbfile_handle.close()

            # Finished downloading PDB
            logger.info(f"Successfully downloaded... {pdbentry.guid} {pdbentry.pdbfile}")

            # Move the temporary file to final location
            final_pdb_file_path = os.path.join(pdb_file_path, f"{sanitize_path_component(pdbentry.pdbfile)}.gzip")
            shutil.move(pdb_tmp_file_path, final_pdb_file_path)
            
        except Exception as e:
            logger.error(f"Error downloading symbol {pdbentry.guid}/{pdbentry.pdbfile}: {e}")
            pdbentry.downloading = False
            crud.modify_pdb_entry(db, pdbentry)
            # Clean up temporary file
            if os.path.exists(pdb_tmp_file_path):
                try:
                    os.remove(pdb_tmp_file_path)
                except OSError:
                    pass
            raise


def get_pdb_size(resp):
    """ Get the size of the PDB buffer being downloaded """

    for header in ["Content-Length", "x-goog-stored-content-length"]:
        if resp.headers.get(header):
            return int(resp.headers[header])

    # Output an error stating the content-length could not be found.
    logger.error(f"Could not get content length from server: {
                 resp.status_code}")
    return None


def get_symbol(pdbname: str, pdbfile: str, guid: str, background_tasks: BackgroundTasks, db: Session, is_gzip_supported: bool):
    # Validate input parameters first, before any file system operations
    try:
        validate_pdb_entry_fields(pdbname, guid, pdbfile)
    except ValueError as e:
        logger.error(f"Invalid parameters in get_symbol: {e}")
        return Response(status_code=400, content=f"Invalid parameters: {e}")
    
    try:
        pdb_file_path = os.path.join(SYMBOL_PATH, 
                                    sanitize_path_component(pdbname), 
                                    sanitize_path_component(guid), 
                                    f"{sanitize_path_component(pdbfile)}.gzip")

        if not os.path.isfile(pdb_file_path):
            # Use helper function to reduce code duplication
            pdbentry = create_or_find_pdb_entry(db, guid, pdbname, pdbfile)
            
            if pdbentry.downloading:
                return Response(status_code=404)
            
            pdbentry.downloading = True
            crud.modify_pdb_entry(db, pdbentry)
            background_tasks.add_task(download_symbol, pdbentry, db)
            return Response(status_code=404)

        # Use helper function to reduce code duplication
        pdbentry = create_or_find_pdb_entry(db, guid, pdbname, pdbfile, True)

        if is_gzip_supported:
            logger.debug("Returning gzip compressed stream...")
            return FileResponse(pdb_file_path, headers={"content-encoding": "gzip"}, media_type="application/octet-stream")

        def stream_decompressed_data(chunk_size=CHUNK_SIZE):
            """Stream decompressed data with memory usage monitoring."""
            bytes_streamed = 0
            with gzip.open(pdb_file_path, 'rb') as gzip_file:
                while True:
                    # Monitor memory usage
                    if bytes_streamed > MAX_MEMORY_USAGE:
                        logger.warning(f"Memory usage limit reached while streaming {pdbfile}")
                        break
                        
                    chunk = gzip_file.read(chunk_size)
                    if not chunk:
                        break
                        
                    bytes_streamed += len(chunk)
                    yield chunk

        logger.debug("Returning decompressed stream...")
        return StreamingResponse(stream_decompressed_data(), media_type="application/octet-stream")
    
    except ValueError as e:
        logger.error(f"Validation error in get_symbol: {e}")
        return Response(status_code=400, content=f"Invalid parameters: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in get_symbol: {e}")
        return Response(status_code=500, content="Internal server error")


@sym.get("/{pdbname}/{guid}/{pdbfile}")
@sym.get("/download/symbols/{pdbname}/{guid}/{pdbfile}")
async def get_symbol_api(pdbname: str, guid: str, pdbfile: str, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        accept_encoding = request.headers.get("Accept-Encoding", "")
        is_gzip_supported = "gzip" in accept_encoding.lower()
        return get_symbol(pdbname, pdbfile, guid, background_tasks, db, is_gzip_supported)
    except ValueError as e:
        logger.error(f"Validation error in get_symbol_api: {e}")
        return Response(status_code=400, content=f"Invalid parameters: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in get_symbol_api: {e}")
        return Response(status_code=500, content="Internal server error")


@sym.get("/symbols")
def get_symbol_entries(db: Session = Depends(get_db)) -> list:
    return jsonable_encoder(db.query(models.SymbolEntry).all())


@sym.on_event("startup")
def fastsym_init():
    db = session_local()
    downloads = crud.find_still_downloading(db)
    for download in downloads:
        try:
            # Use path sanitization for security
            failed_tmp_download = os.path.join(
                SYMBOL_PATH, 
                sanitize_path_component(download.pdbname), 
                sanitize_path_component(download.guid), 
                f"tmp_{sanitize_path_component(download.pdbfile)}.gzip")
            if os.path.exists(failed_tmp_download):
                os.remove(failed_tmp_download)
        except ValueError as e:
            logger.warning(f"Invalid path components in existing download entry: {e}")
        except Exception as e:
            logger.error(f"Error cleaning up failed download: {e}")
            
        download.downloading = False
        crud.modify_pdb_entry(db, download)
