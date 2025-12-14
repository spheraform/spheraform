# Helm Migration - Complete!

The Spheraform project has been successfully migrated from DevSpace to Helm/Skaffold/Tilt.

## What Changed

### New Infrastructure Stack

- **Helm Chart**: Kubernetes manifests are now packaged as a Helm chart at `helm/spheraform/`
- **Skaffold**: Updated to use Helm for deployments with profiles for local, staging, and production
- **Tilt**: Updated to load the Helm chart while maintaining hot-reload functionality
- **Legacy k8s/**: Old raw manifests archived to `k8s-legacy/` for reference

### Key Benefits

1. **Environment Management**: Easy configuration through values files (local, staging, production)
2. **Release Management**: Helm provides rollback, history, and upgrade capabilities
3. **Hot-Reload Preserved**: Tilt still provides fast local development with file sync
4. **Production Ready**: Helm chart works with any Kubernetes cluster

## Quick Start

### Local Development with Tilt (Recommended)

```bash
# Start minikube if not running
minikube start --cpus=4 --memory=8192

# Launch Tilt
tilt up
```

Access services:
- Web UI: http://localhost:5173
- API: http://localhost:8000/docs
- Martin: http://localhost:3000
- MinIO: http://localhost:9001

### Local Development with Skaffold

```bash
# Build and deploy with hot-reload
skaffold dev

# Or deploy without watching
skaffold run -p local
```

### Manual Helm Install

```bash
# Local deployment
helm install spheraform helm/spheraform -f helm/spheraform/values-local.yaml

# Production deployment
helm install spheraform helm/spheraform \
  -f helm/spheraform/values-production.yaml \
  --set api.image.tag=v0.1.0 \
  --set web.image.tag=v0.1.0 \
  --set postgres.password=$POSTGRES_PASSWORD \
  --set minio.rootPassword=$MINIO_PASSWORD \
  -n production --create-namespace
```

## Helm Chart Structure

```
helm/spheraform/
├── Chart.yaml                     # Chart metadata
├── values.yaml                    # Default values
├── values-local.yaml              # Local development overrides
├── values-staging.yaml            # Staging environment
├── values-production.yaml         # Production environment
├── .helmignore                    # Files to ignore
├── README.md                      # Chart documentation
└── templates/
    ├── _helpers.tpl               # Template functions
    ├── NOTES.txt                  # Post-install message
    ├── ingress.yaml               # Optional ingress
    ├── postgres/                  # PostgreSQL templates
    ├── redis/                     # Redis templates
    ├── minio/                     # MinIO templates
    ├── martin/                    # Martin tile server templates
    ├── api/                       # API templates
    └── web/                       # Web templates
```

## Testing the Migration

### Validate Helm Chart

```bash
# Lint the chart
helm lint helm/spheraform

# Test template rendering
helm template spheraform helm/spheraform -f helm/spheraform/values-local.yaml

# Dry run install
helm install spheraform helm/spheraform \
  -f helm/spheraform/values-local.yaml \
  --dry-run --debug
```

### Test in a Clean Namespace

```bash
# Install to test namespace
helm install test-spheraform helm/spheraform \
  -f helm/spheraform/values-local.yaml \
  -n test --create-namespace

# Verify all pods are running
kubectl get pods -n test

# Port-forward to test services
kubectl port-forward -n test svc/test-spheraform-web 5173:5173
kubectl port-forward -n test svc/test-spheraform-api 8000:8000

# Cleanup
helm uninstall test-spheraform -n test
kubectl delete namespace test
```

## Configuration

### Environment-Specific Values

**Local** (`values-local.yaml`):
- `imagePullPolicy: Never` (use local images)
- `standard` storage class
- Single replicas
- No ingress

**Staging** (`values-staging.yaml`):
- Push images to GHCR
- Cloud storage class (e.g., `gp3` for AWS)
- 2 replicas for API and Web
- Ingress with Let's Encrypt staging

**Production** (`values-production.yaml`):
- Push images to GHCR with version tags
- Cloud storage class with larger PVCs
- 3+ replicas for high availability
- Ingress with TLS certificates
- Increased resource limits

### Customizing Values

Override specific values at install/upgrade:

```bash
helm install spheraform helm/spheraform \
  -f helm/spheraform/values-local.yaml \
  --set api.replicas=2 \
  --set postgres.persistence.size=10Gi \
  --set global.storageClass=fast-ssd
```

## Common Operations

### Upgrade

```bash
# Upgrade to new chart or values
helm upgrade spheraform helm/spheraform \
  -f helm/spheraform/values-production.yaml \
  --set api.image.tag=v0.2.0
```

### Rollback

```bash
# Rollback to previous release
helm rollback spheraform

# Rollback to specific revision
helm rollback spheraform 2
```

### View Release History

```bash
helm history spheraform -n production
```

### Uninstall

```bash
helm uninstall spheraform -n production

# Note: PVCs are not deleted automatically
kubectl delete pvc -l app.kubernetes.io/instance=spheraform -n production
```

## Port Forwarding

When not using ingress, access services via port-forward:

```bash
# Web UI
kubectl port-forward svc/spheraform-web 5173:5173

# API
kubectl port-forward svc/spheraform-api 8000:8000

# Martin tile server
kubectl port-forward svc/spheraform-martin 3000:3000

# MinIO console
kubectl port-forward svc/spheraform-minio 9001:9001

# PostgreSQL
kubectl port-forward svc/spheraform-postgres 5432:5432

# Redis
kubectl port-forward svc/spheraform-redis 6379:6379
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -l app.kubernetes.io/instance=spheraform
kubectl describe pod <pod-name>
```

### View Logs

```bash
# API logs
kubectl logs -l app.kubernetes.io/component=api -f

# Web logs
kubectl logs -l app.kubernetes.io/component=web -f

# All Spheraform logs
kubectl logs -l app.kubernetes.io/instance=spheraform --tail=100 -f
```

### Database Connection

```bash
# Connect to PostgreSQL
kubectl exec -it deployment/spheraform-postgres -- psql -U spheraform -d spheraform

# Check connection from API
kubectl exec -it deployment/spheraform-api -- env | grep DATABASE_URL
```

### PVC Issues

```bash
# Check PVC status
kubectl get pvc -l app.kubernetes.io/instance=spheraform

# Describe PVC
kubectl describe pvc spheraform-postgres-data
```

## CI/CD Integration

The migration includes Skaffold profiles for CI/CD:

```yaml
# .github/workflows/deploy.yaml (example)
- name: Deploy to staging
  env:
    PROFILE: staging
    IMAGE_TAG: ${{ github.sha }}
  run: |
    skaffold run -p staging
```

See `skaffold.yaml` for profile configurations.

## Documentation

- Helm Chart: `helm/spheraform/README.md`
- General Deployment: `DEPLOYMENT.md`
- Migration Plan: `/Users/alexey/.claude/plans/dazzling-gathering-sedgewick.md`

## Next Steps

1. ✅ Test local development with Tilt (`tilt up`)
2. ✅ Verify hot-reload works for API and Web
3. ✅ Test Helm install in a clean namespace
4. ⏭️ Set up CI/CD pipeline with Skaffold
5. ⏭️ Create staging environment
6. ⏭️ Configure secrets management for production
7. ⏭️ Set up ingress with TLS certificates

## Rollback Plan

If issues arise, the old k8s/ manifests are preserved:

```bash
# Restore old manifests
mv k8s-legacy k8s

# Or continue using Tilt/Skaffold with old setup
git checkout HEAD~1 Tiltfile skaffold.yaml
```

## Success! 🎉

The migration is complete. All services now deploy via Helm chart while maintaining the same developer experience with Tilt's hot-reload capabilities.

For any issues, check:
- Helm chart documentation: `helm/spheraform/README.md`
- Tilt logs when running `tilt up`
- Kubernetes events: `kubectl get events --sort-by='.lastTimestamp'`
