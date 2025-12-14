# claude.md

## Project overview

The internet is filled with open GIS data, and there is a rich ecosystem of tools to serve this data. We have

- ArcGIS REST
- WFS/WMS/WCS
- CKAN
- FTP
- File servers with Shapefile-zips, GeoJSONs, GeoPackages, File GeoDatabases
- STAC
- S3
- OpenDataHub
- Many custom APIs
- Non-geospatial formats that reference spatial coordiantes (PDFs, CSVs, HTML) when scraped

However no tool exists for indexing all these sources, or viewing and accessing their contents from one place. Spheraform
wishes to fill this gap and make open data accessible to everyone. ArcGIS Online and QGIS are not friendly interfaces and
require accounts.

Spheraform should:

- Be usable without an account
  - Accounts may be used to store data and access history
- Be easy to populate with new sources
- You should be able to paste in a direct link to a dataset and view it immediately
- Have basic analytics tools available through the frontend
- Be accessible programatically using an API
- Be usable with Python bindings
- Run anywhere: deploy on your computer, cloud, server, cluster, toaster. It should be flexible enough to fit any business case

## Target user

- GIS professionals in organisations
- Geospatial, social science, medical researchers
- Members of the public who wish to view open data

## Technical stack

- Backend: Python 3.12, FastAPI
- Frontend: Svelte 5 (TypeScript), Maplibre GL JS
- Cache/Queue: Redis
- Deployment: docker-compose, kubernetes, helm
- Orchstration: Dagster
- Map tiling: Martin
- Geodata cache: PostGIS
- Storage: Object storage - MinIO/S3/GCS
- Connection to dynamic proxy rotation to ensure we can access the data anywhere

## Project Structure

```bash
spheraform/
├── backend/
│   ├── spheraform/
│   │   ├── api/           # FastAPI routers
│   │   ├── adapters/      # Source adapters (arcgis, wfs, ckan, etc.)
│   │   ├── services/      # Business logic
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   └── workers/       # Background job handlers
│   └── tests/
├── frontend/
│   └── src/
├── pipelines/             # Dagster pipelines
├── helm/                  # Kubernetes deployment
├── docker-compose.yml
└── claude.md
```

## Coding standards

- Include type hints on all functions
- Docstrings for public functions and classes
- Document complex business logic with inline comments
- Use async for I/O-bound operations (HTTP, database)
- No GeoPandas in request paths (memory issues). Use Fiona/Shapely for streaming.
- Keep dependencies minimal. Justify new packages.

## Architecture principles

- Keep components small and focused
- Follow RESTful API conventions
- Use consistent error handling patterns
- Separate business logic from API routes
- Adapters are stateless. All state in database or object storage.
- Prefer streaming over loading into memory
- Design for horizontal scaling (stateless workers)

## Error handling

- Use structured exceptions with error codes
- Return consistent error responses: `{"error": "code", "message": "...", "details": {}}`
- Log errors with context (request_id, user_id, dataset_id)
- Never expose internal stack traces to users

## Testing standards

- Unit tests for adapters, services, utilities
- Integration tests for API endpoints
- Use pytest fixtures for database and S3
- Mock external geoservers in tests
- Test with realistic sample data (fixtures in tests/fixtures/)

## Deployment strategy

- Default: docker-compose (local dev, small deployments)
- Production: Kubernetes with Helm chart
- No local PostgreSQL outside containers. Don't check for system psql.
- All config via environment variables
- Secrets via environment or mounted files (never in code)

## API conventions

- All endpoints prefixed with /api/v1/
- Use plural nouns: /datasets, /servers, /jobs
- Pagination: ?limit=100&offset=0
- Filtering: ?theme=hydro&updated_after=2024-01-01
- Sorting: ?sort=-updated_at (- for descending)
- GeoJSON responses for spatial data
- Jobs return 202 Accepted with Location header

## Database conventions

- Use UUIDs for primary keys
- Timestamps: created_at, updated_at (auto-managed)
- Soft deletes where appropriate (deleted_at)
- JSONB for flexible metadata fields
- Index all foreign keys and common query fields

## Git conventions

- Conventional commits: feat:, fix:, docs:, refactor:
- Feature branches: feature/add-wfs-adapter
- PR descriptions explain why, not just what

## Key design decisions

- PostGIS is optional. Metadata can run on plain PostgreSQL.
- Cached geodata stored as GeoParquet/PMTiles in object storage, not PostGIS tables.
- Martin serves tiles from PMTiles on S3, not from PostGIS.
- Source adapters handle pagination internally. Callers get async iterators.
- Change detection before download. Don't re-fetch unchanged data.
- Large datasets (>100k features) use chunked parallel downloads.

## Constraints

- Must work offline (after initial setup) for air-gapped deployments
- Must support self-hosted without cloud dependencies
- No vendor lock-in. All components replaceable.
- Apache 2.0 license

## Out of scope (for now)

- User authentication (optional feature, not core)
- Dataset editing/publishing (read-only aggregator)
- Complex spatial analysis (basic buffer/clip only)
- ML/AI features
