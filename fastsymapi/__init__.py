"""FastSymApi - FastAPI server for symbol caching and downloading."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastsymapi.logging import logger
from fastsymapi.routes import cleanup_stale_downloads, sym
from fastsymapi.sql_db import models
from fastsymapi.sql_db.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown cleanup."""
    cleanup_stale_downloads()
    logger.info("Starting FastSymApi server...")
    yield


def create_app() -> FastAPI:
    """Create the FastAPI application instance."""
    models.Base.metadata.create_all(bind=engine)

    app = FastAPI(lifespan=lifespan)
    app.include_router(sym)
    return app


app = create_app()


@app.get("/health")
def health_check():
    return {"status": "ok"}
