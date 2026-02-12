"""API route handlers for symbol operations.

Single Responsibility: This module defines the HTTP API endpoints
and delegates business logic to the download module.

Dependency Inversion: Route handlers depend on abstractions
(the database session via FastAPI's Depends) rather than
concrete implementations.
"""

import gzip
import os

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from fastsymapi.config import CHUNK_SIZE, MAX_MEMORY_USAGE, SYMBOL_PATH
from fastsymapi.download import create_or_find_pdb_entry, download_symbol
from fastsymapi.logging import logger
from fastsymapi.sql_db import crud, models
from fastsymapi.sql_db.database import get_db, session_local
from fastsymapi.validation import sanitize_path_component, validate_pdb_entry_fields

sym = APIRouter()


def get_symbol(
    pdbname: str,
    pdbfile: str,
    guid: str,
    background_tasks: BackgroundTasks,
    db: Session,
    is_gzip_supported: bool,
) -> Response:
    """Core logic for retrieving or initiating download of a symbol file."""
    try:
        validate_pdb_entry_fields(pdbname, guid, pdbfile)
    except ValueError as e:
        logger.error(f"Invalid parameters in get_symbol: {e}")
        return Response(status_code=400, content=f"Invalid parameters: {e}")

    try:
        pdb_file_path = os.path.join(
            SYMBOL_PATH,
            sanitize_path_component(pdbname),
            sanitize_path_component(guid),
            f"{sanitize_path_component(pdbfile)}.gzip",
        )

        if not os.path.isfile(pdb_file_path):
            pdbentry = create_or_find_pdb_entry(db, guid, pdbname, pdbfile)

            if pdbentry.downloading:
                return Response(status_code=404)

            pdbentry.downloading = True
            crud.modify_pdb_entry(db, pdbentry)
            background_tasks.add_task(download_symbol, pdbentry, db)
            return Response(status_code=404)

        create_or_find_pdb_entry(db, guid, pdbname, pdbfile, True)

        if is_gzip_supported:
            logger.debug("Returning gzip compressed stream...")
            return FileResponse(
                pdb_file_path,
                headers={"content-encoding": "gzip"},
                media_type="application/octet-stream",
            )

        def stream_decompressed_data(chunk_size: int = CHUNK_SIZE):
            """Stream decompressed data with memory usage monitoring."""
            bytes_streamed = 0
            with gzip.open(pdb_file_path, "rb") as gzip_file:
                while True:
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
async def get_symbol_api(
    pdbname: str,
    guid: str,
    pdbfile: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Response:
    """API endpoint for retrieving symbol files."""
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
def get_symbol_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list:
    """List symbol entries in the database with pagination."""
    return jsonable_encoder(db.query(models.SymbolEntry).offset(skip).limit(limit).all())


def cleanup_stale_downloads() -> None:
    """Clean up any downloads that were interrupted by a previous shutdown."""
    db = session_local()
    try:
        downloads = crud.find_still_downloading(db)
        for download in downloads:
            try:
                failed_tmp_download = os.path.join(
                    SYMBOL_PATH,
                    sanitize_path_component(download.pdbname),
                    sanitize_path_component(download.guid),
                    f"tmp_{sanitize_path_component(download.pdbfile)}.gzip",
                )
                if os.path.exists(failed_tmp_download):
                    os.remove(failed_tmp_download)
            except ValueError as e:
                logger.warning(f"Invalid path components in existing download entry: {e}")
            except Exception as e:
                logger.error(f"Error cleaning up failed download: {e}")

            download.downloading = False
            crud.modify_pdb_entry(db, download)
    finally:
        db.close()
