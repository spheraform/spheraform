"""FastAPI application for Spheraform Aggregator."""

import logging
import logging.config
import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers import servers, datasets, search, download
from .workers.download_worker import start_worker_thread
from .workers.crawl_worker import start_crawl_worker_thread

# Structured logging config that writes to stdout so Docker captures it reliably
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        }
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "default",
        }
    },
    "loggers": {
        # root logger
        "": {"handlers": ["stdout"], "level": "DEBUG"},
        # uvicorn loggers
        "uvicorn": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        # Capture logs from core adapters and services
        "spheraform_core": {"handlers": ["stdout"], "level": "DEBUG", "propagate": False},
        # More specific logger for the ArcGIS adapter to ensure messages propagate to root
        "spheraform_core.adapters.arcgis": {"handlers": ["stdout"], "level": "DEBUG", "propagate": True},
    },
}

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Spheraform Aggregator API",
    description="Platform for aggregating geospatial datasets from multiple geoservers",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    debug=True
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(servers.router, prefix="/api/v1/servers", tags=["servers"])
app.include_router(datasets.router, prefix="/api/v1/datasets", tags=["datasets"])
app.include_router(search.router, prefix="/api/v1/search", tags=["search"])
app.include_router(download.router, prefix="/api/v1/download", tags=["download"])


@app.on_event("startup")
async def startup_event():
    """Start background workers on API startup."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not set, background workers will not start")
        return

    logger.info("Starting background workers")
    start_worker_thread(database_url)
    start_crawl_worker_thread(database_url)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Spheraform Aggregator API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )
