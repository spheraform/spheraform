# Spheraform API Usage Examples

This guide shows how to use the Spheraform API with real ArcGIS servers.

## Example Server

**Server:** South Ayrshire Council GIS Server
**Base URL:** `https://gisext.south-ayrshire.gov.uk/server/rest/services`
**Example Layer:** Environment Conservation MapServer Layer 2
**Layer URL:** `https://gisext.south-ayrshire.gov.uk/server/rest/services/Public/EnvironmentConservation/MapServer/2`

## Prerequisites

Start the API server:

```bash
# Start PostgreSQL and other services
docker-compose up -d

# Run database migrations
cd packages/core
DATABASE_URL="postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform" alembic upgrade head

# Start the API
cd ../api
uvicorn spheraform_api.main:app --reload --port 8000
```

## 1. Register the ArcGIS Server

First, add the South Ayrshire GIS server to Spheraform:

```bash
curl -X POST http://localhost:8000/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "South Ayrshire Council GIS",
    "base_url": "https://gisext.south-ayrshire.gov.uk/server/rest/services",
    "provider_type": "arcgis",
    "probe_frequency_hours": 24
  }'
```

**Response:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "South Ayrshire Council GIS",
  "base_url": "https://gisext.south-ayrshire.gov.uk/server/rest/services",
  "provider_type": "arcgis",
  "health_status": "unknown",
  "probe_frequency_hours": 24,
  "dataset_count": 0,
  "active_dataset_count": 0,
  "created_at": "2025-12-01T16:30:00Z",
  "updated_at": "2025-12-01T16:30:00Z"
}
```

Save the `id` for the next steps.

## 2. Check Server Health

Verify the server is accessible:

```bash
# Replace {server_id} with the actual ID from step 1
curl http://localhost:8000/api/v1/servers/{server_id}/health
```

**Response:**
```json
{
  "server_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "healthy": true,
  "checked_at": "2025-12-01T16:31:00Z"
}
```

## 3. Crawl Server to Discover Datasets

Trigger a crawl to discover all layers/datasets from the server:

```bash
curl -X POST http://localhost:8000/api/v1/servers/{server_id}/crawl
```

**Response:**
```json
{
  "server_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "datasets_discovered": 45,
  "datasets_new": 45,
  "datasets_updated": 0,
  "crawl_duration_seconds": 12.5
}
```

This will discover all layers including:
- Public/EnvironmentConservation/MapServer layers
- And all other available services on the server

## 4. List All Discovered Datasets

Get all datasets from the South Ayrshire server:

```bash
curl "http://localhost:8000/api/v1/datasets/?geoserver_id={server_id}"
```

**Response:**
```json
[
  {
    "id": "dataset-uuid-1",
    "name": "Conservation Areas",
    "description": "Conservation areas in South Ayrshire",
    "external_id": "2",
    "access_url": "https://gisext.south-ayrshire.gov.uk/server/rest/services/Public/EnvironmentConservation/MapServer/2",
    "feature_count": 150,
    "themes": ["environment", "conservation"],
    "keywords": ["conservation", "areas", "heritage"],
    "is_active": true,
    "geoserver_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  },
  {
    "id": "dataset-uuid-2",
    "name": "Protected Sites",
    "external_id": "3",
    "access_url": "https://gisext.south-ayrshire.gov.uk/server/rest/services/Public/EnvironmentConservation/MapServer/3",
    "feature_count": 75,
    "themes": ["environment"],
    "is_active": true,
    "geoserver_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
]
```

## 5. Search for Specific Datasets

Search for environment-related datasets:

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "conservation",
    "themes": ["environment"]
  }'
```

**Response:**
```json
{
  "total": 3,
  "results": [
    {
      "id": "dataset-uuid-1",
      "name": "Conservation Areas",
      "description": "Conservation areas in South Ayrshire",
      "access_url": "https://gisext.south-ayrshire.gov.uk/server/rest/services/Public/EnvironmentConservation/MapServer/2",
      "feature_count": 150,
      "themes": ["environment", "conservation"]
    }
  ],
  "facets": {
    "themes": [
      {"value": "environment", "count": 3},
      {"value": "conservation", "count": 2}
    ]
  }
}
```

## 6. Get Specific Dataset Details

Get details for the Environment Conservation layer:

```bash
# First, search for it by name or external_id
curl "http://localhost:8000/api/v1/datasets/?geoserver_id={server_id}&external_id=2"

# Then get full details
curl http://localhost:8000/api/v1/datasets/{dataset_id}
```

**Response:**
```json
{
  "id": "dataset-uuid-1",
  "geoserver_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "external_id": "2",
  "name": "Conservation Areas",
  "description": "Conservation areas designated in South Ayrshire",
  "keywords": ["conservation", "heritage", "protected"],
  "themes": ["environment", "conservation", "admin"],
  "bbox": [-5.5, 55.0, -4.3, 55.6],
  "feature_count": 150,
  "updated_date": "2024-11-15T10:30:00Z",
  "download_formats": ["geojson", "json"],
  "access_url": "https://gisext.south-ayrshire.gov.uk/server/rest/services/Public/EnvironmentConservation/MapServer/2",
  "download_strategy": "simple",
  "is_active": true,
  "created_at": "2025-12-01T16:35:00Z",
  "updated_at": "2025-12-01T16:35:00Z"
}
```

## 7. Preview Dataset Features

Get a sample of features from the layer (limited to 10 features):

```bash
curl http://localhost:8000/api/v1/datasets/{dataset_id}/preview
```

**Response:**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": 1,
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-4.75, 55.45], [-4.75, 55.46], [-4.74, 55.46], [-4.74, 55.45], [-4.75, 55.45]]]
      },
      "properties": {
        "OBJECTID": 1,
        "NAME": "Ayr Town Centre Conservation Area",
        "DESIGNATION_DATE": "1977-05-20",
        "AREA_HA": 45.2
      }
    }
  ]
}
```

## 8. Download Dataset

### Small Dataset (< 1000 features) - Direct Download

```bash
curl -X POST http://localhost:8000/api/v1/download/ \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_ids": ["dataset-uuid-1"],
    "format": "geojson"
  }'
```

**Response (immediate for small datasets):**
```json
{
  "status": "completed",
  "download_url": "/tmp/spheraform_downloads/dataset_1234567890.geojson",
  "size_bytes": 125000,
  "feature_count": 150
}
```

### Large Dataset - Background Job

For datasets with >10,000 features, a background job is created:

```bash
curl -X POST http://localhost:8000/api/v1/download/ \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_ids": ["large-dataset-uuid"],
    "format": "geojson"
  }'
```

**Response:**
```json
{
  "status": "pending",
  "job_id": "job-uuid-1234",
  "message": "Download job created. Use job_id to check status."
}
```

Check job status:

```bash
curl http://localhost:8000/api/v1/download/jobs/{job_id}
```

**Response:**
```json
{
  "id": "job-uuid-1234",
  "status": "in_progress",
  "dataset_id": "large-dataset-uuid",
  "format": "geojson",
  "total_chunks": 10,
  "completed_chunks": 3,
  "progress_percent": 30,
  "created_at": "2025-12-01T16:40:00Z"
}
```

Download when complete:

```bash
curl http://localhost:8000/api/v1/download/jobs/{job_id}/download -o conservation_areas.geojson
```

## 9. Spatial Search

Search for datasets that intersect with a specific area (e.g., Ayr town center):

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "bbox": [-4.65, 55.45, -4.60, 55.48],
    "themes": ["environment"]
  }'
```

**Response:**
```json
{
  "total": 5,
  "results": [
    {
      "id": "dataset-uuid-1",
      "name": "Conservation Areas",
      "feature_count": 150
    },
    {
      "id": "dataset-uuid-5",
      "name": "Tree Preservation Orders",
      "feature_count": 89
    }
  ]
}
```

## 10. Update Server Configuration

Update crawl frequency or other settings:

```bash
curl -X PUT http://localhost:8000/api/v1/servers/{server_id} \
  -H "Content-Type: application/json" \
  -d '{
    "probe_frequency_hours": 12,
    "name": "South Ayrshire Council GIS (Production)"
  }'
```

## 11. List All Registered Servers

```bash
curl http://localhost:8000/api/v1/servers/
```

## 12. Filter Datasets by Theme

Get all conservation-related datasets:

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "themes": ["conservation"]
  }'
```

## Python Example

```python
import requests

# Configuration
BASE_URL = "http://localhost:8000"
ARCGIS_SERVER = "https://gisext.south-ayrshire.gov.uk/server/rest/services"

# 1. Register server
response = requests.post(
    f"{BASE_URL}/servers/",
    json={
        "name": "South Ayrshire Council GIS",
        "base_url": ARCGIS_SERVER,
        "provider_type": "arcgis",
        "probe_frequency_hours": 24
    }
)
server = response.json()
server_id = server["id"]
print(f"Server registered: {server_id}")

# 2. Crawl to discover datasets
response = requests.post(f"{BASE_URL}/servers/{server_id}/crawl")
crawl_result = response.json()
print(f"Discovered {crawl_result['datasets_discovered']} datasets")

# 3. Search for conservation areas
response = requests.post(
    f"{BASE_URL}/search/",
    json={
        "query": "conservation",
        "themes": ["environment"]
    }
)
search_results = response.json()

for dataset in search_results["results"]:
    print(f"- {dataset['name']}: {dataset['access_url']}")

    # 4. Download dataset
    download_response = requests.post(
        f"{BASE_URL}/download/",
        json={
            "dataset_ids": [dataset["id"]],
            "format": "geojson"
        }
    )

    download_result = download_response.json()

    if download_result["status"] == "completed":
        print(f"  Downloaded: {download_result['download_url']}")
    else:
        print(f"  Job created: {download_result['job_id']}")
```

## JavaScript/Node.js Example

```javascript
const axios = require('axios');

const BASE_URL = 'http://localhost:8000';
const ARCGIS_SERVER = 'https://gisext.south-ayrshire.gov.uk/server/rest/services';

async function main() {
  // 1. Register server
  const serverResponse = await axios.post(`${BASE_URL}/servers/`, {
    name: 'South Ayrshire Council GIS',
    base_url: ARCGIS_SERVER,
    provider_type: 'arcgis',
    probe_frequency_hours: 24
  });

  const serverId = serverResponse.data.id;
  console.log(`Server registered: ${serverId}`);

  // 2. Crawl to discover datasets
  const crawlResponse = await axios.post(`${BASE_URL}/servers/${serverId}/crawl`);
  console.log(`Discovered ${crawlResponse.data.datasets_discovered} datasets`);

  // 3. Search for datasets
  const searchResponse = await axios.post(`${BASE_URL}/search/`, {
    query: 'conservation',
    themes: ['environment']
  });

  for (const dataset of searchResponse.data.results) {
    console.log(`- ${dataset.name}: ${dataset.access_url}`);

    // 4. Get dataset preview
    const previewResponse = await axios.get(`${BASE_URL}/datasets/${dataset.id}/preview`);
    console.log(`  Features: ${previewResponse.data.features.length}`);
  }
}

main().catch(console.error);
```

## Common Workflows

### Workflow 1: Discover and catalog a new ArcGIS server

1. Register server (`POST /servers/`)
2. Check health (`GET /servers/{id}/health`)
3. Crawl server (`POST /servers/{id}/crawl`)
4. List discovered datasets (`GET /datasets/?geoserver_id={id}`)

### Workflow 2: Find and download specific data

1. Search datasets (`POST /search/`)
2. Get dataset details (`GET /datasets/{id}`)
3. Preview features (`GET /datasets/{id}/preview`)
4. Download (`POST /download/`)

### Workflow 3: Monitor dataset changes

1. Register server with crawl frequency
2. Automatic crawls will detect changes
3. Query datasets with `change_detected=true`
4. Re-download changed datasets

## Notes

- The API automatically detects the download strategy based on feature count
- Small datasets (<1000 features) download immediately
- Large datasets create background jobs
- All GeoJSON downloads use WGS84 (EPSG:4326)
- Spatial search uses PostGIS functions (requires PostGIS-enabled database)
