"""SQLAlchemy ORM models for symbol entries."""

from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint

from fastsymapi.sql_db.database import Base


class SymbolEntry(Base):
    __tablename__ = "symbolentry"
    id = Column(Integer, primary_key=True, index=True, unique=True)
    guid = Column(String, index=True)
    pdbname = Column(String, index=True)
    pdbfile = Column(String, index=True)
    downloading = Column(Boolean, index=True, default=False)
    found = Column(Boolean, index=True, default=False)

    __table_args__ = (UniqueConstraint("guid", "pdbfile"),)
