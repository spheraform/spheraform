# Spheraform

A platform that aggregates geospatial datasets from multiple geoservers into one searchable catalogue. Users can discover data by location, download it in various formats, and export to their own systems.

## Features

- **Multi-Source Support**: ArcGIS REST (WFS, WCS, CKAN, GeoServer, S3 coming soon)
- **Smart Change Detection**: Probe sources cheaply before downloading
- **Intelligent Downloads**: Automatic strategy selection (paged, parallel, chunked) based on dataset size
- **Multiple Export Formats**: GeoJSON, GeoParquet, PMTiles (GeoPackage, Shapefile, MBTiles coming soon)
- **Spatial Search**: Find datasets by bounding box with PostGIS spatial indexing
- **Vector Tiles**: Fast map rendering with PMTiles served from object storage
- **Map-First Web Interface**: Full-screen map with floating glassmorphism UI
- **Flexible Deployment**: Docker Compose or Kubernetes

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
├── helm/              # Kubernetes Helm charts
├── scripts/           # Utility scripts (backups, maintenance)
├── alembic/           # Database migrations
├── tests/             # Test suite
├── docs/              # Documentation
├── docker-compose.yml # Docker Compose deployment
└── Tiltfile           # Tilt configuration for local Kubernetes development
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
- **Celery Workers**: Background job processing

### Local Kubernetes Development (Recommended)

For local development with Kubernetes using Tilt:

```bash
# Start Minikube (if not already running)
minikube start --cpus=4 --memory=8192

# Start Tilt (builds images, deploys to k8s, enables hot-reload)
tilt up

# View Tilt UI
open http://localhost:10350
```

**Tilt provides:**
- Automatic Docker image building with live updates
- Hot-reload for Python and Svelte code changes
- Real-time logs from all services
- Easy service restarts and debugging
- Production-like Kubernetes environment locally

**Access services** (via Tilt port-forwards):
- **Web UI**: http://localhost:5173
- **API Docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)
- **Flower (Celery)**: http://localhost:5555

**To stop:**
```bash
tilt down
```

### Docker Compose Development

If you prefer running services individually without Kubernetes:

```bash
# Start infrastructure only
docker-compose up -d postgres redis minio

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

### Production Kubernetes Deployment

For production deployment to Kubernetes, you can use Skaffold, Helm, or kubectl:

#### Option 1: Skaffold (Recommended for CI/CD)

```bash
# Deploy to production
PROFILE=production skaffold run

# Deploy to staging
PROFILE=staging skaffold run

# Continuous deployment with hot-reload (staging)
PROFILE=staging skaffold dev
```

#### Option 2: Helm

```bash
# Deploy using Helm
helm install spheraform ./helm/spheraform \
  -f ./helm/spheraform/values-production.yaml \
  --set minio.publicEndpoint=https://your-minio-domain.com \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=your-domain.com \
  --namespace production --create-namespace

# Upgrade existing deployment
helm upgrade spheraform ./helm/spheraform \
  -f ./helm/spheraform/values-production.yaml \
  --namespace production
```

#### Option 3: kubectl

```bash
# Generate manifests from Helm chart
helm template spheraform ./helm/spheraform \
  -f ./helm/spheraform/values-production.yaml > k8s-manifests.yaml

# Apply to cluster
kubectl apply -f k8s-manifests.yaml
```

**Check deployment status:**
```bash
kubectl get pods -n production
kubectl get services -n production
kubectl logs -f deployment/spheraform-api -n production
```

**Production checklist:**
- [ ] Update MinIO credentials in `values-production.yaml`
- [ ] Configure container registry (e.g., GHCR, Docker Hub)
- [ ] Set image tags to specific versions (not `latest`)
- [ ] Configure ingress with your domain
- [ ] Set up SSL/TLS certificates
- [ ] Configure persistent volumes for production storage class
- [ ] Review resource limits and requests
- [ ] Set up monitoring and logging
- [ ] Configure backups for PostgreSQL

See `helm/spheraform/values.yaml` for all configuration options.

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
- **Queue**: Redis + Celery (async job processing)
- **Storage**: MinIO (S3-compatible object storage for GeoParquet/PMTiles)
- **Tiles**: PMTiles (vector tiles served directly from object storage)
- **Orchestration**: Celery Beat (scheduled tasks)
- **Frontend**: SvelteKit + MapLibre GL JS + PMTiles protocol
- **Deployment**: Docker Compose (local) or Kubernetes (Helm/Skaffold)

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

Apache 2.0
