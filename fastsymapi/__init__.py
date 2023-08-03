from fastapi import FastAPI
from fastsymapi.sql_db import models
from fastsymapi.logging import logger
from fastsymapi.sql_db.database import engine
from fastsymapi.symbols import sym
import click

def create_app():
    """ Create the application context """

    # Create the database tables 
    models.base.metadata.create_all(bind=engine)

    # instantiate FastAPI 
    app = FastAPI()

    # Symbol API 
    app.include_router(sym)

    logger.info("Starting FastSymApi server...")
    
    return app

app = create_app()