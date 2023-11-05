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


def download_symbol(pdbname: str, pdbfile: str, guid: str, db: Session) -> None:
    """ Iterate over SYM_URLs looking for the requested PDB file """

    # If the content-encoding flag is found, switch this to true
    is_gzip_supported = False

    # Retrieve the PDB entry
    pdbentry = crud.find_pdb_entry(db, guid, pdbfile)

    # Iterate over the symbol server URLs
    for sym_url in SYM_URLS:

        # Check if symbol exists on the server
        symbol_url = sym_url + f"/{pdbname}/{guid}/{pdbfile}"
        resp = requests.get(
            symbol_url, stream=True)

        # If the symbol was found download it
        if resp.status_code == 200:

            # Set PDB entry to found
            pdbentry.found = True

            # Notify that the download is beginning
            downloading_msg = (
                "Downloading... "
                + click.style(guid, bold=True)
                + " "
                + click.style(pdbfile, bold=True)
            )
            logger.warning(downloading_msg)

            # Create the PDB directory with GUID if it does not exist
            pdb_file_path = os.path.join(SYMBOL_PATH, pdbname, guid)
            if not os.path.exists(pdb_file_path):
                os.makedirs(pdb_file_path)

            # Logic that identifies whether its a gzip or not
            content_encoding = resp.headers.get("Content-Encoding", "")
            is_gzip_supported = "gzip" in content_encoding.lower()

            # Create the PDB file and iterate over it writing the chunks
            pdb_tmp_file_path = os.path.join(
                pdb_file_path, "tmp_"+pdbfile+".gzip")

            # if the file is already compressed, just write the raw bytes
            if is_gzip_supported:
                pdbfile_handle = open(pdb_tmp_file_path, 'wb')

            # else, we must compress it ourselves
            else:
                pdbfile_handle = gzip.open(pdb_tmp_file_path, 'wb')

            # Get the size of the PDB buffer being downloaded
            if resp.headers.get("Content-Length"):
                pdb_size = int(resp.headers["Content-Length"])
            elif resp.headers.get("x-goog-stored-content-length"):
                pdb_size = int(resp.headers["x-goog-stored-content-length"])
            else:
                # Output an error stating the content-length could not be found.
                content_len_error = (
                        "Could not get content length from server: "
                        + click.style(symbol_url, bold=True)
                        + " "
                        + click.style(resp.status_code, bold=True)
                )
                logger.error(content_len_error)

                # Set the PDB entry to no longer downloading 
                pdbentry.downloading = False
                crud.modify_pdb_entry(db, pdbentry)
                return

            downloaded = 0
            percent = 0
            while downloaded < pdb_size:
                remaining = pdb_size - downloaded
                chunk = resp.raw.read((min(CHUNK_SIZE, remaining)))
                pdbfile_handle.write(chunk)
                downloaded += len(chunk)
                percent = int((downloaded/pdb_size)*100)
                if percent % 5 == 0:
                    percentage_msg = (
                        "Downloading... "
                        + click.style(guid, bold=True)
                        + " "
                        + click.style(pdbfile, bold=True)
                        + " "
                        + click.style(str(percent)+"%", reverse=True)
                    )
                    logger.warning(percentage_msg)

            # Close the file handle
            pdbfile_handle.close()

            # Finished downloading PDB
            success_msg = (
                "Successfully downloaded... "
                + click.style(guid, bold=True)
                + " "
                + click.style(pdbfile, bold=True)
            )
            logger.info(success_msg)

            # If the file is already a gzip, there is no need to compress it
            pdb_file_path = os.path.join(pdb_file_path, pdbfile+".gzip")
            shutil.move(pdb_tmp_file_path, pdb_file_path)
            break

        # Unable to find PDB at any of the Symbol Servers
        else:
            download_percentage = (
                "Could not find symbol: "
                + click.style(symbol_url, bold=True)
                + " "
                + click.style(resp.status_code, bold=True)
            )
            logger.debug(download_percentage)

    # Set the PDB entry to 'finished' downloading
    pdbentry.downloading = False
    crud.modify_pdb_entry(db, pdbentry)

    return


def get_symbol(pdbname: str, pdbfile: str, guid: str, background_tasks: BackgroundTasks, db: Session, is_gzip_supported: bool):
    """
    Attempt to return a locally cached PDB, either compressed or uncompressed. 
    If the PDB is not cached, return a 404, and start a background task
    to attempt to download and cache the PDB.
    """

    # Check if symbol already exists - all PDB's are stored compressed
    pdb_file_path = os.path.join(SYMBOL_PATH, pdbname, guid, pdbfile+".gzip")

    # If the file does not exist, download it
    if not os.path.isfile(pdb_file_path):

        # Check if there is a record of the PDB entry
        pdbentry = crud.find_pdb_entry(db, guid, pdbfile)

        # If not, create a new one
        if not pdbentry:
            pdbentry = crud.create_pdb_entry(db, guid, pdbname, pdbfile)

        # Check if the PDB is still downloading, and 404 if it is
        if pdbentry.downloading:
            symbol_still_downloading = (
                "Symbol still downloading... "
                + click.style(guid, bold=True)
                + " "
                + click.style(pdbfile, bold=True, reverse=True)
            )
            logger.warning(symbol_still_downloading)
            return Response(status_code=404)

        # Set the PDB entry to downloading before kicking off the background task
        pdbentry.downloading = True
        crud.modify_pdb_entry(db, pdbentry)

        # Kick off a background task to download the symbol
        background_tasks.add_task(download_symbol, pdbname, pdbfile, guid, db)

        # 404, there is no PDB to return but it will be downloaded shortly
        return Response(status_code=404)

    # Check if PDB entry exists, database may have been deleted
    # create a new entry if that is the case.
    # helps keep symbol entries accurate to whats cached.
    pdbentry = crud.find_pdb_entry(db, guid, pdbfile)
    if not pdbentry:
        pdbentry = crud.create_pdb_entry(db, guid, pdbname, pdbfile, True)

    # Return the gzipped PDB
    if is_gzip_supported:
        logger.debug("Returning gzip compressed stream...")
        return FileResponse(pdb_file_path, headers={"content-encoding": "gzip"}, media_type="application/octet-stream")

    # If gzip is not supported, decompress and stream the uncompressed data
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
    """ Returns a PDB file, or attempts starts a background task to download it.  """

    # Check whether GZIP encoding is accepted
    accept_encoding = request.headers.get("Accept-Encoding", "")
    is_gzip_supported = "gzip" in accept_encoding.lower()

    return get_symbol(pdbname, pdbfile, guid, background_tasks, db, is_gzip_supported)


@sym.get("/symbols")
def get_symbol_entries(db: Session = Depends(get_db)) -> list:
    """ 
    Return a JSON list of every symbol requested, whether they were found 
    or are still currently being downloaded. 
    """

    return jsonable_encoder(db.query(models.SymbolEntry).all())


@sym.on_event("startup")
def fastsym_init():
    """
    Finds all PDB Entries listed as 'still downloading' and delete's their
    tmp files. It's likely FastSymApi crashed and the downloads did not finish. 
    """
    db = session_local()
    downloads = crud.find_still_downloading(db)
    for download in downloads:
        failed_tmp_download = os.path.join(
                SYMBOL_PATH, download.pdbname, download.guid, "tmp_"+download.pdbfile+".gzip")
        if os.path.exists(failed_tmp_download):
            os.remove(failed_tmp_download)
        download.downloading = False
        crud.modify_pdb_entry(db, download)
