from sqlalchemy.orm import Session
from fastsymapi.sql_db import models

def find_pdb_entry(db: Session, guid: str, pdbfile: str):
    """ Find a PDB entry """
    return db.query(models.SymbolEntry).filter(models.SymbolEntry.guid == guid, 
                                               models.SymbolEntry.pdbfile == pdbfile).first()

def find_still_downloading(db: Session):
    """ Return all still downloading PDB entries """
    return db.query(models.SymbolEntry).filter(models.SymbolEntry.downloading == True).all()

def create_pdb_entry(db: Session, guid: str, pdbname: str, pdbfile: str, found: bool = False):
    """ Create a new PDB entry """
    pdb_entry = models.SymbolEntry(pdbname=pdbname, guid=guid, pdbfile=pdbfile, found=found)
    db.add(pdb_entry)
    db.commit()
    db.refresh(pdb_entry)
    return pdb_entry

def modify_pdb_entry(db: Session, pdbentry: models.SymbolEntry) -> None:
    """ Modify a PDB entry """
    db.add(pdbentry)
    db.commit()
    db.refresh(pdbentry)