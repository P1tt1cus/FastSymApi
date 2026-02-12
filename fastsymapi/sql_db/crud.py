"""CRUD operations for symbol entries.

Single Responsibility: This module handles all database
create/read/update operations for SymbolEntry records.
"""

from sqlalchemy.orm import Session

from fastsymapi.sql_db import models


def find_pdb_entry(db: Session, guid: str, pdbfile: str) -> models.SymbolEntry | None:
    """Find a PDB entry by guid and pdbfile."""
    return (
        db.query(models.SymbolEntry)
        .filter(models.SymbolEntry.guid == guid, models.SymbolEntry.pdbfile == pdbfile)
        .first()
    )


def find_still_downloading(db: Session) -> list[models.SymbolEntry]:
    """Return all PDB entries that are still marked as downloading."""
    return db.query(models.SymbolEntry).filter(models.SymbolEntry.downloading == True).all()  # noqa: E712


def create_pdb_entry(db: Session, guid: str, pdbname: str, pdbfile: str, found: bool = False) -> models.SymbolEntry:
    """Create a new PDB entry."""
    pdb_entry = models.SymbolEntry(pdbname=pdbname, guid=guid, pdbfile=pdbfile, found=found)
    db.add(pdb_entry)
    db.commit()
    db.refresh(pdb_entry)
    return pdb_entry


def modify_pdb_entry(db: Session, pdbentry: models.SymbolEntry) -> None:
    """Update an existing PDB entry."""
    db.add(pdbentry)
    db.commit()
    db.refresh(pdbentry)
