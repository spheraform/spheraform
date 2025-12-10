# DevSpace Configuration

This directory contains DevSpace configuration files for deploying Spheraform to Kubernetes (including Minikube).

## Files

- **devspace-api.yaml** - API backend configuration
- **devspace-postgres.yaml** - PostgreSQL + PostGIS database configuration
- **devspace-redis.yaml** - Redis cache configuration
- **devspace-minio.yaml** - MinIO S3-compatible object storage configuration

## Quick Start

From the project root directory:

```bash
# Deploy all services to Kubernetes
devspace deploy

# Start development mode with hot-reload
devspace dev

# Clean up all deployments
devspace purge
```

## Architecture

The main `devspace.yaml` (in the project root) references these component files as dependencies:

```
spheraform (root)
├── api (devspace-api.yaml)
│   ├── postgres (devspace-postgres.yaml)
│   └── minio (devspace-minio.yaml)
├── martin (tile server)
└── web (frontend)
```

## Storage

Configured for Minikube with reduced storage requirements:
- PostgreSQL: 2Gi (needs more for PostGIS spatial data)
- Redis: 1Gi
- MinIO: 1Gi
- **Total: 4Gi**

## Development

All components support hot-reload in development mode:
- API: Syncs `packages/api` and `packages/core`
- Web: Syncs `packages/web`
- Martin: Syncs `config/`

## Ports

When running `devspace dev`, the following ports are forwarded to localhost:

- **5173** - Web frontend
- **8000** - API backend
- **3000** - Martin tile server
- **5432** - PostgreSQL (when debugging database)
- **6379** - Redis (when debugging cache)
- **9000** - MinIO API
- **9001** - MinIO Console

## Notes

- All configurations use the DevSpace component-chart for simplified Kubernetes deployments
- Volumes use `storageClassName: standard` for Minikube compatibility
- Services are configured to restart automatically on failure
