# Tilt Development Environment

Tilt provides fast, reliable Kubernetes development with live updates and easy debugging.

**Note**: Tilt is for **local development only**. For production deployments, use Skaffold, Helm, or kubectl. See the main README for production deployment instructions.

## Quick Start

```bash
# Start Minikube (if not running)
minikube start --cpus=4 --memory=8192

# Start Tilt
tilt up

# View Tilt UI
open http://localhost:10350
```

## What Tilt Does

Tilt automatically:
- **Builds Docker images** for API and Web services
- **Deploys to Kubernetes** using Helm charts
- **Live updates code** without full rebuilds:
  - Python files sync instantly to API containers
  - Svelte files sync instantly to Web containers
- **Manages port-forwards** for easy access
- **Streams logs** from all services in one view
- **Watches Helm charts** and redeploys on changes

## Architecture

Tilt manages all Spheraform components:

```
Tilt
├── Docker Images (with live updates)
│   ├── spheraform-api (Python/FastAPI)
│   └── spheraform-web (SvelteKit)
│
├── Kubernetes Resources (via Helm)
│   ├── PostgreSQL + PostGIS
│   ├── Redis
│   ├── MinIO (S3-compatible storage)
│   ├── API Deployment
│   ├── Web Deployment
│   ├── Celery Workers (download, crawl)
│   ├── Celery Beat (scheduler)
│   └── Flower (Celery monitoring)
│
└── Port Forwards
    ├── 5173 → Web UI
    ├── 8000 → API
    ├── 9000 → MinIO API
    ├── 9001 → MinIO Console
    ├── 5555 → Flower
    ├── 5432 → PostgreSQL
    └── 6379 → Redis
```

## Live Updates

Tilt syncs code changes without rebuilding images:

### API Live Updates
- **Synced files**: `packages/api/**/*.py`, `packages/core/**/*.py`
- **Trigger rebuild**: Changes to `pyproject.toml`
- **Runs**: `pip install -e` when dependencies change

### Web Live Updates
- **Synced files**: `packages/web/src/**/*`, `packages/web/static/**/*`
- **Trigger rebuild**: Changes to `package.json`
- **Runs**: `npm install` when dependencies change

## Accessing Services

When Tilt is running, access services at:

| Service | URL | Description |
|---------|-----|-------------|
| **Web UI** | http://localhost:5173 | Main application interface |
| **API Docs** | http://localhost:8000/docs | FastAPI Swagger UI |
| **MinIO Console** | http://localhost:9001 | Object storage admin (minioadmin/minioadmin) |
| **Flower** | http://localhost:5555 | Celery task monitoring |
| **Tilt UI** | http://localhost:10350 | Development dashboard |

## Tilt UI Features

The Tilt UI (http://localhost:10350) shows:

- **Resource status**: Green = healthy, Red = errors
- **Build logs**: See Docker build output
- **Pod logs**: Stream logs from all containers
- **Trigger buttons**: Manually rebuild or restart services
- **Endpoints**: Quick links to all services

## Common Commands

```bash
# Start Tilt (foreground)
tilt up

# Start Tilt in background
tilt up &

# View Tilt status
tilt get uiresource

# Restart a specific resource
tilt trigger spheraform-api

# Stop Tilt
tilt down

# View logs for a specific resource
tilt logs spheraform-api
```

## Custom Buttons

Tilt provides custom buttons in the UI for common tasks:

| Button | Description | Command |
|--------|-------------|---------|
| **helm-lint** | Validate Helm chart | `helm lint ./helm/spheraform` |
| **db-shell** | Connect to PostgreSQL | `kubectl exec -it deployment/spheraform-postgres -- psql` |
| **redis-cli** | Connect to Redis | `kubectl exec -it deployment/spheraform-redis -- redis-cli` |
| **api-logs** | Stream API logs | `kubectl logs -f deployment/spheraform-api` |
| **backup-now** | Trigger manual backup | Creates backup job from cronjob |
| **backup-list** | List available backups | Shows backups in volume |
| **backup-health** | Check backup status | Runs health check script |

## Debugging

### View logs
```bash
# Via Tilt UI (recommended)
open http://localhost:10350

# Via kubectl
kubectl logs -f deployment/spheraform-api
kubectl logs -f deployment/spheraform-web
kubectl logs -f deployment/spheraform-celery-download
```

### Access pod shell
```bash
kubectl exec -it deployment/spheraform-api -- /bin/bash
```

### Check pod status
```bash
kubectl get pods
kubectl describe pod <pod-name>
```

### Database access
```bash
# Via custom button in Tilt UI, or:
kubectl exec -it deployment/spheraform-postgres -- psql -U spheraform -d spheraform
```

## Troubleshooting

### Tilt won't start
```bash
# Check Minikube status
minikube status

# Start Minikube if needed
minikube start --cpus=4 --memory=8192

# Check kubectl context
kubectl config current-context
```

### Images not building
```bash
# Set Docker environment to Minikube
eval $(minikube docker-env)

# Manually build images
docker build -t spheraform-api:latest -f packages/api/Dockerfile .
docker build -t spheraform-web:latest -f packages/web/Dockerfile .
```

### Pods crashing
```bash
# Check pod logs
kubectl logs <pod-name>

# Check pod events
kubectl describe pod <pod-name>

# Check resource usage
kubectl top pods
```

### Port conflicts
```bash
# Check what's using ports
lsof -i :5173
lsof -i :8000

# Kill process using port
kill -9 <PID>
```

## Helm Chart Configuration

Tilt uses these Helm configurations:

- **Chart**: `./helm/spheraform`
- **Values**: `./helm/spheraform/values-local.yaml`
- **Image pull policy**: `Never` (uses local images from Minikube Docker)

To modify Kubernetes resources, edit:
- `Tiltfile` - Tilt configuration
- `helm/spheraform/values-local.yaml` - Local overrides
- `helm/spheraform/values.yaml` - Default values
- `helm/spheraform/templates/**/*.yaml` - Kubernetes manifests

## Performance Tips

1. **Use SSD storage** for Minikube VM
2. **Allocate enough resources**: Minimum 4 CPUs, 8GB RAM
3. **Exclude node_modules**: Already configured in `.dockerignore`
4. **Use live_update** instead of full rebuilds when possible
5. **Close unused resources** in Tilt UI to reduce CPU usage

## Production Deployment

Tilt is for local development only. For production deployments, use:

### Option 1: Skaffold (Recommended for CI/CD)

```bash
# Deploy to production
PROFILE=production skaffold run

# Deploy to staging
PROFILE=staging skaffold run
```

### Option 2: Helm

```bash
# Deploy to production cluster
helm install spheraform ./helm/spheraform \
  -f ./helm/spheraform/values-production.yaml \
  --namespace production --create-namespace
```

### Option 3: kubectl

```bash
# Generate manifests
helm template spheraform ./helm/spheraform \
  -f ./helm/spheraform/values-production.yaml > k8s-manifests.yaml

# Apply to cluster
kubectl apply -f k8s-manifests.yaml
```

See the main README for complete production deployment instructions.
