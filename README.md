# Spheraform

A platform that aggregates geospatial datasets from multiple geoservers into one searchable catalogue. Users can discover data by location, download it in various formats, and export to their own systems.

## Features

- **Multi-Source Support**: ArcGIS REST (WFS, WCS, CKAN, GeoServer, S3 coming soon)
- **Smart Change Detection**: Probe sources cheaply before downloading
- **Intelligent Downloads**: Automatic strategy selection (paged, parallel, chunked) based on dataset size
- **Multiple Export Formats**: GeoJSON (GeoPackage, Shapefile, MBTiles, PostGIS coming soon)
- **Spatial Search**: Find datasets by bounding box with PostGIS spatial indexing
- **Vector Tiles**: Fast map rendering with Martin tile server
- **Map-First Web Interface**: Full-screen map with floating glassmorphism UI
- **Docker Deployment**: One-command deployment with Docker Compose

## Project Structure

```
spheraform/
├── packages/
│   ├── core/          # Core library (models, adapters, business logic)
│   ├── api/           # FastAPI backend
│   ├── web/           # SvelteKit frontend (map-first UI)
│   ├── cli/           # Command-line interface (Typer) [planned]
│   ├── client/        # Python SDK [planned]
│   └── pipelines/     # Dagster orchestration [planned]
├── alembic/           # Database migrations
├── tests/             # Test suite
└── docker-compose.yml # Full-stack deployment
```

## Quick Start

**See [QUICKSTART.md](./QUICKSTART.md) for detailed instructions**

### One-Command Deployment (Recommended)

```bash
# Start all services with Docker Compose
docker-compose up -d

# Access the web interface
open http://localhost:5173
```

This starts:
- **Web Interface**: http://localhost:5173
- **API Backend**: http://localhost:8000/docs
- **PostgreSQL + PostGIS**: localhost:5432
- **Redis**: localhost:6379
- **MinIO S3 Storage**: http://localhost:9001
- **Martin Tile Server**: http://localhost:3000

### Development Setup

If you prefer running services individually:

```bash
# Start infrastructure only
docker-compose up -d postgres redis minio martin

# Run migrations
cd packages/api
DATABASE_URL="postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform" \
  alembic upgrade head

# Run API
DATABASE_URL="postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform" \
  uvicorn spheraform_api.main:app --reload --port 8000

# Run web interface
cd packages/web
npm install
npm run dev
```

Visit:
- **Web UI**: http://localhost:5173
- **API Docs**: http://localhost:8000/docs

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

- **Backend**: FastAPI (async Python with httpx)
- **Database**: PostgreSQL + PostGIS (spatial indexing with GIST)
- **Queue**: Redis (job queue - planned)
- **Storage**: MinIO (S3-compatible object storage)
- **Tiles**: Martin (PostGIS → MVT vector tiles)
- **Orchestration**: Dagster (planned)
- **Frontend**: SvelteKit + MapLibre GL JS
- **Deployment**: Docker Compose (multi-stage builds)

## Documentation

- [Quick Start Guide](./QUICKSTART.md) - Get up and running in minutes
- [Web Interface Deployment](./packages/web/DEPLOYMENT.md) - Production deployment
- [API Documentation](./packages/api/README.md) - Backend API details
- [Web UI Documentation](./packages/web/README.md) - Frontend development

### Implemented Features

✅ **Core**:
- ArcGIS REST API adapter (FeatureServer)
- Parallel and paged download strategies
- Proxy support with country-based routing
- PostGIS spatial search (bbox with ST_Intersects/ST_Contains/ST_Within)
- WKT geometry parsing and validation

✅ **API**:
- Server management (CRUD + crawl)
- Dataset listing with spatial filtering
- Preview endpoint (sample GeoJSON)
- Download endpoint (direct file download)
- FastAPI with async support

✅ **Web Interface**:
- Full-screen MapLibre GL map
- Floating glassmorphism UI (no top bar)
- Server management (add, list, crawl)
- Dataset browsing and download
- Responsive design

### Planned Features

🔜 **Coming Soon**:
- Dataset bbox visualization on map
- Draw-on-map bbox search
- Analytics dashboard
- Job queue with progress tracking
- More data sources (WFS, WCS, CKAN)
- More export formats (GeoPackage, Shapefile, MBTiles)
- CLI interface
- Python SDK

## License

MIT
