"""FastAPI application for Spheraform Aggregator."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers import servers, datasets, search, download

# Create FastAPI app
app = FastAPI(
    title="Spheraform Aggregator API",
    description="Platform for aggregating geospatial datasets from multiple geoservers",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
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
