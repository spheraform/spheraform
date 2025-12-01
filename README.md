# GeoData Aggregator

A platform that aggregates geospatial datasets from multiple geoservers into one searchable catalogue. Users can discover data by location, download it in various formats, and export to their own systems.

## Features

- **Multi-Source Support**: ArcGIS REST, WFS, WCS, CKAN, GeoServer, S3, and more
- **Smart Change Detection**: Probe sources cheaply before downloading
- **Intelligent Downloads**: Automatic strategy selection based on dataset size
- **Multiple Export Formats**: GeoJSON, GeoPackage, Shapefile, MBTiles, PostGIS, and more
- **Spatial Search**: Find datasets by location or bounding box
- **Vector Tiles**: Fast map rendering with Martin tile server
- **Three Interfaces**: Web GUI, CLI, and Python library

## Project Structure

```
spheraform-aggregator/
├── packages/
│   ├── core/          # Core library (models, adapters, business logic)
│   ├── api/           # FastAPI backend
│   ├── cli/           # Command-line interface (Typer)
│   ├── client/        # Python SDK
│   └── pipelines/     # Dagster orchestration
├── web/               # React frontend
├── alembic/           # Database migrations
├── tests/             # Test suite
└── docker-compose.yml # Local development infrastructure
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Node.js 18+ (for web frontend)

### 1. Clone and Setup

```bash
# Copy environment variables
cp .env.example .env

# Start infrastructure (PostgreSQL, Redis, MinIO, Martin)
docker-compose up -d

# Install dependencies (using uv or pip)
uv sync  # or: pip install -e packages/core packages/api packages/cli
```

### 2. Initialize Database

```bash
# Run migrations
alembic upgrade head
```

### 3. Run the API

```bash
cd packages/api
uvicorn spheraform_api.main:app --reload
```

Visit: http://localhost:8000/docs for API documentation

### 4. Use the CLI

```bash
# List servers
spheraform servers list

# Add a new server
spheraform servers add --name "Oregon GIS" --url "https://..." --type arcgis

# Search for datasets
spheraform search --point 45.52,-122.68 --buffer 10km
```

### 5. Run the Web UI

```bash
cd web
npm install
npm run dev
```

Visit: http://localhost:5173

## Development

### Running Tests

```bash
pytest tests/
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Code Quality

```bash
# Lint with ruff
ruff check .

# Format
ruff format .
```

## Architecture

- **Backend**: FastAPI (async Python)
- **Database**: PostgreSQL + PostGIS
- **Queue**: Redis + Celery
- **Storage**: MinIO (S3-compatible)
- **Tiles**: Martin (PostGIS → MVT)
- **Orchestration**: Dagster
- **Frontend**: React + MapLibre GL JS

## Documentation

See `/docs` for detailed documentation on:
- Supported geoserver types
- Download strategies
- Change detection mechanisms
- Export formats
- Deployment guide

## License

MIT
