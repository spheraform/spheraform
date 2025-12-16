#!/bin/bash
# Monitor storage backend usage across datasets

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Spheraform Storage Backend Monitor ===${NC}\n"

# Function to run SQL query
run_query() {
    local query="$1"
    if kubectl get pods >/dev/null 2>&1; then
        kubectl exec deployment/spheraform-postgres -- bash -c "PGPASSWORD=spheraform_dev psql -h localhost -U spheraform -d spheraform -c \"$query\""
    else
        docker-compose exec -T postgres psql -U spheraform -d spheraform -c "$query"
    fi
}

# Summary by storage backend
echo -e "${GREEN}Storage Backend Summary:${NC}"
run_query "
SELECT
  CASE
    WHEN use_s3_storage THEN 'S3/MinIO'
    ELSE 'PostGIS'
  END as storage_backend,
  COUNT(*) as datasets,
  SUM(feature_count) as total_features,
  ROUND(SUM(cache_size_bytes) / 1024.0 / 1024.0, 2) as size_mb
FROM datasets
WHERE is_cached = true
GROUP BY use_s3_storage
ORDER BY use_s3_storage;
"

echo ""
echo -e "${GREEN}Recent Datasets by Storage Backend:${NC}"
run_query "
SELECT
  LEFT(name, 40) as dataset_name,
  feature_count,
  CASE
    WHEN use_s3_storage THEN 'S3/MinIO'
    ELSE 'PostGIS'
  END as backend,
  storage_format,
  ROUND(cache_size_bytes / 1024.0, 2) as size_kb,
  TO_CHAR(cached_at, 'YYYY-MM-DD HH24:MI') as cached_at
FROM datasets
WHERE is_cached = true
ORDER BY cached_at DESC
LIMIT 10;
"

echo ""
echo -e "${GREEN}Storage by Feature Count Range:${NC}"
run_query "
SELECT
  feature_range,
  datasets,
  in_s3,
  in_postgis
FROM (
  SELECT
    CASE
      WHEN feature_count < 1000 THEN '< 1K'
      WHEN feature_count < 10000 THEN '1K - 10K'
      WHEN feature_count < 100000 THEN '10K - 100K'
      ELSE '> 100K'
    END as feature_range,
    CASE
      WHEN feature_count < 1000 THEN 1
      WHEN feature_count < 10000 THEN 2
      WHEN feature_count < 100000 THEN 3
      ELSE 4
    END as sort_order,
    COUNT(*) as datasets,
    SUM(CASE WHEN use_s3_storage THEN 1 ELSE 0 END) as in_s3,
    SUM(CASE WHEN NOT use_s3_storage THEN 1 ELSE 0 END) as in_postgis
  FROM datasets
  WHERE is_cached = true
  GROUP BY feature_range, sort_order
) subq
ORDER BY sort_order;
"

echo ""
echo -e "${YELLOW}Threshold: >= 10,000 features → Object Storage (S3/MinIO/GCS/Azure)${NC}"
echo -e "${YELLOW}Current Mode: STORAGE_BACKEND=\$(kubectl exec deployment/spheraform-api -- env | grep STORAGE_BACKEND)${NC}"
