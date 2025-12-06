# Spheraform Quick Start

Get Spheraform up and running in minutes with Docker Compose.

## Prerequisites

- Docker and Docker Compose installed
- 8GB+ RAM recommended
- Ports available: 5173 (web), 8000 (api), 5432 (postgres), 6379 (redis), 9000-9001 (minio), 3000 (martin)

## Start All Services

```bash
# Clone the repository
git clone <repository-url>
cd spheraform

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

## Access the Services

- **Web Interface**: http://localhost:5173
- **API Documentation**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)
- **Martin Tiles**: http://localhost:3000

## First Steps

1. **Open the Web Interface** at http://localhost:5173
2. **Click the menu bubble** (top left) to open the sidebar
3. **Go to Servers tab** and click "Add Server"
4. **Add your first ArcGIS server**:
   - Name: `Natural England`
   - URL: `https://services.arcgis.com/JJzESW51TqeY9uat/ArcGIS/rest/services`
   - Country: `GB`
5. **Click "Crawl"** to discover datasets
6. **Go to Datasets tab** to browse discovered datasets
7. **Click download** on any dataset to get GeoJSON

## Common Commands

```bash
# Stop all services
docker-compose down

# Restart a specific service
docker-compose restart web
docker-compose restart api

# Rebuild after code changes
docker-compose up -d --build web
docker-compose up -d --build api

# View logs for specific service
docker-compose logs -f web
docker-compose logs -f api

# Clean up everything (including data!)
docker-compose down -v
```

## Development Mode

If you want to run services individually for development:

```bash
# Start infrastructure only
docker-compose up -d postgres redis minio martin

# Run API locally
cd packages/api
DATABASE_URL="postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform" \
  uvicorn spheraform_api.main:app --reload --port 8000

# Run web interface locally
cd packages/web
npm install
npm run dev
```

## Troubleshooting

### Port Already in Use

```bash
# Check what's using the port
lsof -ti:5173  # or 8000, 5432, etc.

# Kill the process
lsof -ti:5173 | xargs kill -9
```

### Database Connection Issues

```bash
# Check if postgres is running
docker-compose ps postgres

# Restart postgres
docker-compose restart postgres

# View postgres logs
docker-compose logs postgres
```

### API Not Responding

```bash
# Check API logs
docker-compose logs api

# Restart API
docker-compose restart api

# Rebuild API
docker-compose up -d --build api
```

### Web Interface Not Loading

```bash
# Check web logs
docker-compose logs web

# Restart web
docker-compose restart web

# Rebuild web
docker-compose up -d --build web
```

## Next Steps

- Read [API Documentation](./packages/api/README.md)
- Read [Web Interface Documentation](./packages/web/README.md)
- Read [Deployment Guide](./packages/web/DEPLOYMENT.md)
- Explore the [Architecture](./ARCHITECTURE.md)
