# Storage Backend Naming Convention

## Overview

The storage backend has been renamed from "S3 storage" to "object storage" to better reflect that it supports multiple object storage providers, not just Amazon S3.

## Supported Object Storage Providers

- **Amazon S3** - AWS cloud object storage
- **MinIO** - Self-hosted S3-compatible storage
- **Google Cloud Storage (GCS)** - Google cloud object storage
- **Azure Blob Storage** - Microsoft cloud object storage
- **DigitalOcean Spaces** - S3-compatible storage
- **Cloudflare R2** - S3-compatible storage
- **Any S3-compatible storage**

## Environment Variable Changes

### Before
```bash
STORAGE_BACKEND=hybrid  # Options: postgis, s3, hybrid
USE_S3_FOR_LARGE_DATASETS=true
MIN_FEATURES_FOR_S3=10000
```

### After
```bash
STORAGE_BACKEND=hybrid  # Options: postgis, object_storage, hybrid
USE_OBJECT_STORAGE_FOR_LARGE_DATASETS=true
MIN_FEATURES_FOR_OBJECT_STORAGE=10000
```

## STORAGE_BACKEND Options

| Value | Description |
|-------|-------------|
| `postgis` | Always use PostGIS for all datasets |
| `object_storage` | Always use object storage (MinIO/S3/GCS/Azure) for all datasets |
| `hybrid` | Smart routing: PostGIS for small datasets (<10k features), object storage for large datasets |

## Code Changes

### API Response
**Before:**
```json
{
  "storage_backend": "s3",
  "s3_data_key": "datasets/...",
  "s3_tiles_key": "datasets/..."
}
```

**After:**
```json
{
  "storage_backend": "object_storage",
  "s3_data_key": "datasets/...",
  "s3_tiles_key": "datasets/..."
}
```

Note: Field names `s3_data_key` and `s3_tiles_key` are kept for backward compatibility, even though they work with any object storage provider.

### Log Messages
**Before:**
```
Dataset has 14,523 features (>= 10,000), using S3 storage
Using S3 storage backend for Dataset Name
```

**After:**
```
Dataset has 14,523 features (>= 10,000), using object storage
Using object storage backend for Dataset Name
```

## Database Fields (Unchanged)

The following database fields retain their `s3_` prefix for backward compatibility:

- `datasets.use_s3_storage` (boolean)
- `datasets.s3_data_key` (varchar)
- `datasets.s3_tiles_key` (varchar)

These fields work with **any** object storage provider, not just S3.

## Migration Guide

If you have existing deployments:

1. **Update environment variables:**
   ```bash
   # Old
   STORAGE_BACKEND=s3
   USE_S3_FOR_LARGE_DATASETS=true
   MIN_FEATURES_FOR_S3=10000

   # New
   STORAGE_BACKEND=object_storage
   USE_OBJECT_STORAGE_FOR_LARGE_DATASETS=true
   MIN_FEATURES_FOR_OBJECT_STORAGE=10000
   ```

2. **Restart API pods/containers:**
   ```bash
   # Kubernetes
   kubectl rollout restart deployment/spheraform-api

   # Docker Compose
   docker-compose restart api
   ```

3. **No database migration needed** - database schema remains unchanged

## Why This Change?

**Problem:** The name "S3" implied Amazon-specific storage, confusing users deploying with MinIO, GCS, or Azure.

**Solution:** Use generic "object storage" terminology that accurately describes the system's capability to work with any S3-compatible or cloud object storage.

**Benefits:**
- Clearer for self-hosted deployments using MinIO
- More accurate for multi-cloud deployments
- Better reflects the system's flexibility
- Reduces vendor lock-in perception
