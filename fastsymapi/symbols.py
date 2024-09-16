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

sym = APIRouter()

CHUNK_SIZE = 1024*1024*2

SYMBOL_PATH = os.path.join(os.path.dirname(__file__), "symbols")

SYM_URLS = [
    "http://msdl.microsoft.com/download/symbols",
    "http://chromium-browser-symsrv.commondatastorage.googleapis.com",
    "http://symbols.mozilla.org",
    "http://symbols.mozilla.org/try"
]


def download_symbol(pdbentry: models.SymbolEntry, db: Session) -> None:
    """ Iterate over SYM_URLs looking for the requested PDB file """

    # Iterate over the symbol server URLs
    for sym_url in SYM_URLS:

        # Check if symbol exists on the server
        symbol_url = sym_url + \
            f"/{pdbentry.pdbname}/{pdbentry.guid}/{pdbentry.pdbfile}"
        resp = requests.get(symbol_url, stream=True)

        # If the symbol was found download it
        if resp.status_code == 200:
            pdbentry.found = True
            download_and_save_symbol(pdbentry, resp, db)
            break

        # Unable to find PDB at any of the Symbol Servers
        else:
            logger.debug(f"Could not find symbol: {
                         symbol_url} {resp.status_code}")

    # Set the PDB entry to 'finished' downloading
    pdbentry.downloading = False
    crud.modify_pdb_entry(db, pdbentry)


def download_and_save_symbol(pdbentry, resp, db):
    """ Download the symbol and save it to disk """

    # Notify that the download is beginning
    logger.warning(f"Downloading... {pdbentry.guid} {pdbentry.pdbfile}")

    # Create the PDB directory with GUID if it does not exist
    pdb_file_path = os.path.join(SYMBOL_PATH, pdbentry.pdbname, pdbentry.guid)
    if not os.path.exists(pdb_file_path):
        os.makedirs(pdb_file_path)

    # Logic that identifies whether its a gzip or not
    content_encoding = resp.headers.get("Content-Encoding", "")
    is_gzip_supported = "gzip" in content_encoding.lower()

    # Create the PDB file and iterate over it writing the chunks
    pdb_tmp_file_path = os.path.join(
        pdb_file_path, "tmp_"+pdbentry.pdbfile+".gzip")

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
        return

    # Dpwnload percentage calculation
    downloaded = 0
    percent = 0
    last_logged_percent = -1
    while downloaded < pdb_size:
        remaining = pdb_size - downloaded
        chunk = resp.raw.read(min(CHUNK_SIZE, remaining))
        pdbfile_handle.write(chunk)
        downloaded += len(chunk)
        percent = int((downloaded / pdb_size) * 100)
        if percent // 5 > last_logged_percent:  # Log every 5%
            last_logged_percent = percent // 5
            logger.warning(f"Downloading... {pdbentry.guid} {
                           pdbentry.pdbfile} {percent}%")

    # Close the file handle
    pdbfile_handle.close()

    # Finished downloading PDB
    logger.info(f"Successfully downloaded... {
                pdbentry.guid} {pdbentry.pdbfile}")

    # If the file is already a gzip, there is no need to compress it
    pdb_file_path = os.path.join(pdb_file_path, pdbentry.pdbfile+".gzip")
    shutil.move(pdb_tmp_file_path, pdb_file_path)


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
    pdb_file_path = os.path.join(SYMBOL_PATH, pdbname, guid, pdbfile+".gzip")

    if not os.path.isfile(pdb_file_path):
        pdbentry = crud.find_pdb_entry(db, guid, pdbfile)
        if not pdbentry:
            pdbentry = crud.create_pdb_entry(db, guid, pdbname, pdbfile)
        if pdbentry.downloading:
            return Response(status_code=404)
        pdbentry.downloading = True
        crud.modify_pdb_entry(db, pdbentry)
        background_tasks.add_task(download_symbol, pdbentry, db)
        return Response(status_code=404)

    pdbentry = crud.find_pdb_entry(db, guid, pdbfile)
    if not pdbentry:
        pdbentry = crud.create_pdb_entry(db, guid, pdbname, pdbfile, True)

    if is_gzip_supported:
        logger.debug("Returning gzip compressed stream...")
        return FileResponse(pdb_file_path, headers={"content-encoding": "gzip"}, media_type="application/octet-stream")

    def stream_decompressed_data(chunk_size=CHUNK_SIZE):
        with gzip.open(pdb_file_path, 'rb') as gzip_file:
            while True:
                chunk = gzip_file.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    logger.debug("Returning decompressed stream...")
    return StreamingResponse(stream_decompressed_data(), media_type="application/octet-stream")


@sym.get("/{pdbname}/{guid}/{pdbfile}")
@sym.get("/download/symbols/{pdbname}/{guid}/{pdbfile}")
async def get_symbol_api(pdbname: str, guid: str, pdbfile: str, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    accept_encoding = request.headers.get("Accept-Encoding", "")
    is_gzip_supported = "gzip" in accept_encoding.lower()
    return get_symbol(pdbname, pdbfile, guid, background_tasks, db, is_gzip_supported)


@sym.get("/symbols")
def get_symbol_entries(db: Session = Depends(get_db)) -> list:
    return jsonable_encoder(db.query(models.SymbolEntry).all())


@sym.on_event("startup")
def fastsym_init():
    db = session_local()
    downloads = crud.find_still_downloading(db)
    for download in downloads:
        failed_tmp_download = os.path.join(
            SYMBOL_PATH, download.pdbname, download.guid, "tmp_"+download.pdbfile+".gzip")
        if os.path.exists(failed_tmp_download):
            os.remove(failed_tmp_download)
        download.downloading = False
        crud.modify_pdb_entry(db, download)
