#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════════════════════╗"
echo "║           Spheraform Celery Integration Test                             ║"
echo "╚══════════════════════════════════════════════════════════════════════════╝"
echo ""

API_BASE="http://localhost:8000/api/v1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "📋 Prerequisites:"
echo "   ✓ Kubernetes cluster running (minikube/docker-desktop/kind)"
echo "   ✓ Tilt is running (tilt up)"
echo "   ✓ All pods are ready"
echo ""

# Check if API is accessible
echo "${YELLOW}1. Checking API connectivity...${NC}"
if curl -s -f "${API_BASE}/health" > /dev/null; then
    echo "${GREEN}   ✓ API is accessible${NC}"
else
    echo "${RED}   ✗ API is not accessible at ${API_BASE}${NC}"
    exit 1
fi

# Check if Flower is accessible
echo "${YELLOW}2. Checking Flower (Celery monitoring)...${NC}"
if curl -s -f "http://localhost:5555" > /dev/null; then
    echo "${GREEN}   ✓ Flower UI is accessible at http://localhost:5555${NC}"
else
    echo "${YELLOW}   ⚠ Flower UI not accessible (check port forward)${NC}"
fi

# Test 1: Create a test geoserver
echo ""
echo "${YELLOW}3. Creating test geoserver...${NC}"
SERVER_RESPONSE=$(curl -s -X POST "${API_BASE}/servers" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ArcGIS Sample Server (Integration Test)",
    "base_url": "https://sampleserver6.arcgisonline.com/arcgis/rest/services",
    "provider_type": "arcgis",
    "probe_frequency_hours": 24
  }')

SERVER_ID=$(echo $SERVER_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "${GREEN}   ✓ Created server: ${SERVER_ID}${NC}"

# Test 2: Trigger crawl job (tests Celery crawl worker)
echo ""
echo "${YELLOW}4. Triggering crawl job (tests Celery crawl worker)...${NC}"
CRAWL_RESPONSE=$(curl -s -X POST "${API_BASE}/servers/${SERVER_ID}/crawl")
CRAWL_JOB_ID=$(echo $CRAWL_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "${GREEN}   ✓ Created crawl job: ${CRAWL_JOB_ID}${NC}"
echo "   Status: queued → Celery worker will process it"

# Monitor crawl job
echo ""
echo "${YELLOW}5. Monitoring crawl job progress...${NC}"
for i in {1..30}; do
    sleep 2
    JOB_STATUS=$(curl -s "${API_BASE}/servers/crawl/${CRAWL_JOB_ID}" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['status'], data.get('datasets_discovered', 0))")
    STATUS=$(echo $JOB_STATUS | awk '{print $1}')
    DATASETS=$(echo $JOB_STATUS | awk '{print $2}')

    echo "   Attempt $i/30: status=$STATUS, datasets_discovered=$DATASETS"

    if [ "$STATUS" == "completed" ]; then
        echo "${GREEN}   ✓ Crawl completed! Discovered $DATASETS datasets${NC}"
        break
    elif [ "$STATUS" == "failed" ]; then
        echo "${RED}   ✗ Crawl failed${NC}"
        curl -s "${API_BASE}/servers/crawl/${CRAWL_JOB_ID}" | python3 -m json.tool
        exit 1
    fi

    if [ $i -eq 30 ]; then
        echo "${RED}   ✗ Timeout waiting for crawl to complete${NC}"
        exit 1
    fi
done

# Test 3: Get a dataset and trigger download job
echo ""
echo "${YELLOW}6. Getting a dataset for download test...${NC}"
DATASET_RESPONSE=$(curl -s "${API_BASE}/datasets?limit=1&geoserver_id=${SERVER_ID}")
DATASET_ID=$(echo $DATASET_RESPONSE | python3 -c "import sys, json; datasets=json.load(sys.stdin); print(datasets[0]['id'] if datasets else '')")

if [ -z "$DATASET_ID" ]; then
    echo "${RED}   ✗ No datasets found${NC}"
    exit 1
fi

DATASET_NAME=$(echo $DATASET_RESPONSE | python3 -c "import sys, json; datasets=json.load(sys.stdin); print(datasets[0]['name'] if datasets else '')")
echo "${GREEN}   ✓ Found dataset: $DATASET_NAME (${DATASET_ID})${NC}"

# Test 4: Trigger download job (tests Celery download worker)
echo ""
echo "${YELLOW}7. Triggering download job (tests Celery download worker)...${NC}"
DOWNLOAD_RESPONSE=$(curl -s -X POST "${API_BASE}/download" \
  -H "Content-Type: application/json" \
  -d "{
    \"dataset_ids\": [\"${DATASET_ID}\"],
    \"format\": \"geojson\"
  }")

DOWNLOAD_JOB_ID=$(echo $DOWNLOAD_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))")
if [ -z "$DOWNLOAD_JOB_ID" ]; then
    echo "${RED}   ✗ Failed to create download job${NC}"
    echo $DOWNLOAD_RESPONSE | python3 -m json.tool
    exit 1
fi
echo "${GREEN}   ✓ Created download job: ${DOWNLOAD_JOB_ID}${NC}"

# Monitor download job
echo ""
echo "${YELLOW}8. Monitoring download job progress...${NC}"
for i in {1..30}; do
    sleep 2
    JOB_DATA=$(curl -s "${API_BASE}/download/jobs/${DOWNLOAD_JOB_ID}")
    STATUS=$(echo $JOB_DATA | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")
    PROGRESS=$(echo $JOB_DATA | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('progress', 0) or 0)")
    STAGE=$(echo $JOB_DATA | python3 -c "import sys, json; print(json.load(sys.stdin).get('current_stage', 'unknown'))")

    echo "   Attempt $i/30: status=$STATUS, stage=$STAGE, progress=${PROGRESS}%"

    if [ "$STATUS" == "completed" ]; then
        echo "${GREEN}   ✓ Download completed!${NC}"
        break
    elif [ "$STATUS" == "failed" ]; then
        echo "${RED}   ✗ Download failed${NC}"
        echo $JOB_DATA | python3 -m json.tool
        exit 1
    fi

    if [ $i -eq 30 ]; then
        echo "${RED}   ✗ Timeout waiting for download to complete${NC}"
        exit 1
    fi
done

# Summary
echo ""
echo "╔══════════════════════════════════════════════════════════════════════════╗"
echo "║                          Test Results                                     ║"
echo "╚══════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "${GREEN}✓ All integration tests passed!${NC}"
echo ""
echo "Tested components:"
echo "  ✓ Celery crawl worker - discovered datasets from ArcGIS server"
echo "  ✓ Celery download worker - downloaded and cached dataset"
echo "  ✓ Redis message broker - job queueing"
echo "  ✓ Database - job tracking and status updates"
echo ""
echo "Next steps:"
echo "  • View Flower dashboard: http://localhost:5555"
echo "  • Check worker logs: kubectl logs deployment/spheraform-celery-download"
echo "  • Monitor with Tilt UI: press 'space' in tilt terminal"
echo ""
