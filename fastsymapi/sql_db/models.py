from sqlalchemy import Column, Integer, String, Boolean, UniqueConstraint
from fastsymapi.sql_db.database import base

class SymbolEntry(base):
    __tablename__ = "symbolentry"
    id = Column(Integer, primary_key=True, index=True, unique=True)
    guid = Column(String, index=True)
    pdbname = Column(String, index=True)
    pdbfile = Column(String, index=True)
    downloading = Column(Boolean, index=True, default=False)
    found = Column(Boolean, index=True, default=False)

    # Adds a unique constraint on the guid, pdbfile 
    __table_args__ = (UniqueConstraint('guid', 'pdbfile'),)

