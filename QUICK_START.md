# Spheraform Quick Start Guide

## Prerequisites
- Docker/Colima running
- Python 3.12 with dependencies installed

## Step 1: Start Docker Services

```bash
# If using Colima
colima start

# Start PostgreSQL, Redis, MinIO
docker-compose up -d

# Verify containers are running
docker ps
```

You should see:
- `spheraform-postgres` on port 5432
- `spheraform-redis` on port 6379
- `spheraform-minio` on ports 9000-9001

## Step 2: Setup Database

```bash
# Drop and recreate schema (if needed)
docker exec spheraform-postgres psql -U spheraform -d spheraform -c "
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO spheraform;
CREATE EXTENSION IF NOT EXISTS postgis;
"

# Run migrations
cd /Users/alexey/Documents/code/spheraform
DATABASE_URL="postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform" \
alembic upgrade head
```

## Step 3: Verify Database

```bash
# Check tables were created
docker exec spheraform-postgres psql -U spheraform -d spheraform -c "\dt"
```

You should see tables:
- geoservers
- datasets
- themes
- download_jobs
- download_chunks
- export_jobs
- change_checks

## Step 4: Start API Server

```bash
cd packages/api
uvicorn spheraform_api.main:app --reload --port 8000
```

## Step 5: Test API

Open another terminal and test:

```bash
# Check API is running
curl http://localhost:8000/

# Should return:
# {"message":"Spheraform API","version":"0.1.0","status":"ok"}
```

## Step 6: Register Your First Server

```bash
# Register South Ayrshire Council GIS server
curl -X POST http://localhost:8000/servers/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "South Ayrshire Council GIS",
    "base_url": "https://gisext.south-ayrshire.gov.uk/server/rest/services",
    "provider_type": "arcgis",
    "probe_frequency_hours": 24
  }'
```

Save the `id` from the response.

## Step 7: Discover Datasets

```bash
# Replace {server_id} with the actual ID from step 6
curl -X POST http://localhost:8000/servers/{server_id}/crawl
```

##  Step 8: Search Datasets

```bash
# List all datasets
curl "http://localhost:8000/datasets/?geoserver_id={server_id}"

# Search for conservation areas
curl -X POST http://localhost:8000/search/ \
  -H "Content-Type: application/json" \
  -d '{
    "query": "conservation",
    "themes": ["environment"]
  }'
```

## Troubleshooting

### Port 5432 Already in Use

If you have an SSH tunnel or local postgres using port 5432:

```bash
# Find what's using the port
lsof -i :5432

# Kill it
kill $(lsof -t -i:5432)
```

### Docker Not Running

```bash
colima stop
colima start
```

### Cannot Connect to Database

```bash
# Test connection via Docker
docker exec spheraform-postgres psql -U spheraform -c "SELECT current_database();"

# If that works but host connection fails, check for port conflicts
lsof -i :5432
```

### Migration Fails

```bash
# Reset database completely
docker exec spheraform-postgres psql -U spheraform -d spheraform -c "
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO spheraform;
"

# Re-run migration
DATABASE_URL="postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform" \
alembic upgrade head
```

## Next Steps

See `API_EXAMPLES.md` for complete API usage examples with:
- Python code examples
- JavaScript/Node.js examples
- All API endpoints documented
- Real-world workflows

## API Endpoints Summary

- `GET /` - API info
- `GET /health` - Health check
- `POST /servers/` - Register new server
- `GET /servers/` - List servers
- `POST /servers/{id}/crawl` - Discover datasets
- `GET /datasets/` - List datasets
- `POST /search/` - Search datasets
- `POST /download/` - Download datasets
- `GET /download/jobs/{id}` - Check download status

For complete documentation, visit: http://localhost:8000/docs (Swagger UI)
