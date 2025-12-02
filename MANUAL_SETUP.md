# Manual Setup Guide - Spheraform

Follow these steps to set up Spheraform manually.

## Step 1: Fix Docker/Colima

```bash
# Check Colima status
colima status

# If not running, start it
colima start

# Verify Docker works
docker ps
```

If you still get "Cannot connect to Docker daemon", restart your terminal or run:
```bash
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
```

## Step 2: Start Docker Services

```bash
cd /Users/alexey/Documents/code/spheraform

# Stop any existing containers
docker-compose down

# Start services (without titiler which doesn't support ARM64)
docker-compose up -d postgres redis minio martin
```

## Step 3: Verify Containers Are Running

```bash
docker ps
```

You should see:
- `spheraform-postgres` (port 5432)
- `spheraform-redis` (port 6379)
- `spheraform-minio` (ports 9000-9001)
- `spheraform-martin` (port 3000)

## Step 4: Setup Database

```bash
# Drop and recreate schema
docker exec spheraform-postgres psql -U spheraform -d spheraform -c "
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO spheraform;
CREATE EXTENSION IF NOT EXISTS postgis;
"
```

## Step 5: Run Migrations

**IMPORTANT:** Make sure no SSH tunnel is using port 5432:

```bash
# Check for SSH tunnels
lsof -i :5432

# If anything is there, kill it:
kill $(lsof -t -i:5432)
```

Now run the migration:

```bash
cd /Users/alexey/Documents/code/spheraform

DATABASE_URL="postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform" \
alembic upgrade head
```

## Step 6: Verify Database Tables

```bash
docker exec spheraform-postgres psql -U spheraform -d spheraform -c "\dt"
```

You should see these tables:
- geoservers
- datasets
- themes
- download_jobs
- download_chunks
- export_jobs
- change_checks

## Step 7: Start API Server

```bash
cd /Users/alexey/Documents/code/spheraform/packages/api

uvicorn spheraform_api.main:app --reload --port 8000
```

## Step 8: Test the API

Open a new terminal and test:

```bash
# Test API is running
curl http://localhost:8000/

# Should return:
# {"message":"Spheraform API","version":"0.1.0","status":"ok"}
```

## Step 9: Register South Ayrshire Server

```bash
curl -X POST http://localhost:8000/servers/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "South Ayrshire Council GIS",
    "base_url": "https://gisext.south-ayrshire.gov.uk/server/rest/services",
    "provider_type": "arcgis",
    "probe_frequency_hours": 24
  }'
```

**Save the `id` from the response!**

## Step 10: Discover Datasets

```bash
# Replace {server_id} with the ID from step 9
SERVER_ID="paste-your-id-here"

curl -X POST "http://localhost:8000/servers/$SERVER_ID/crawl"
```

This will discover all datasets including the Environment Conservation layer.

## Step 11: List Discovered Datasets

```bash
curl "http://localhost:8000/datasets/?geoserver_id=$SERVER_ID" | python3 -m json.tool
```

## Step 12: Search for Specific Dataset

```bash
curl -X POST http://localhost:8000/search/ \
  -H "Content-Type: application/json" \
  -d '{
    "query": "conservation",
    "geoserver_id": "'$SERVER_ID'"
  }' | python3 -m json.tool
```

## Common Issues

### Issue: Port 5432 in use

**Solution:**
```bash
# Find what's using it
lsof -i :5432

# Kill SSH tunnels
kill $(lsof -t -i:5432 | grep ssh)
```

### Issue: Docker not connecting

**Solution:**
```bash
# Restart Colima
colima stop
colima start

# Or restart from Docker Desktop if using that
```

### Issue: Migration fails

**Solution:**
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

### Issue: API can't connect to database

**Solution:**
```bash
# Test connection directly
docker exec spheraform-postgres psql -U spheraform -c "SELECT version();"

# If that works, check for port conflicts
lsof -i :5432
```

## Success Checklist

- [ ] Docker containers running (`docker ps`)
- [ ] Database tables created (Step 6)
- [ ] API server running (Step 7)
- [ ] API responds at http://localhost:8000 (Step 8)
- [ ] Server registered (Step 9)
- [ ] Datasets discovered (Step 10)

## Next Steps

Once everything is working:

1. Check out `API_EXAMPLES.md` for complete API documentation
2. View API docs at http://localhost:8000/docs (Swagger UI)
3. Access your data at http://localhost:8000/datasets/

## Quick Reference

```bash
# Start services
docker-compose up -d postgres redis minio martin

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# Start API
cd packages/api && uvicorn spheraform_api.main:app --reload --port 8000

# Test API
curl http://localhost:8000/
```
