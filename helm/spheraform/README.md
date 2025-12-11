# Spheraform Helm Chart

This Helm chart deploys Spheraform, a platform that aggregates geospatial datasets from multiple geoservers into one searchable catalogue.

## Prerequisites

- Kubernetes 1.24+
- Helm 3.12+
- PersistentVolume provisioner support in the underlying infrastructure
- (Optional) Ingress controller for production deployments

## Installing the Chart

### Local Development

```bash
# Install with local development settings
helm install spheraform . -f values-local.yaml

# Or specify namespace
helm install spheraform . -f values-local.yaml -n dev --create-namespace
```

### Staging Environment

```bash
helm install spheraform . -f values-staging.yaml \
  --set api.image.tag=git-abc123 \
  --set web.image.tag=git-abc123 \
  -n staging --create-namespace
```

### Production Environment

```bash
helm install spheraform . -f values-production.yaml \
  --set api.image.tag=v0.1.0 \
  --set web.image.tag=v0.1.0 \
  --set postgres.password=$POSTGRES_PASSWORD \
  --set minio.rootPassword=$MINIO_PASSWORD \
  -n production --create-namespace
```

## Uninstalling the Chart

```bash
helm uninstall spheraform -n <namespace>
```

**Note:** PersistentVolumeClaims are not deleted automatically. To delete them:

```bash
kubectl delete pvc -l app.kubernetes.io/instance=spheraform -n <namespace>
```

## Configuration

The following table lists the configurable parameters of the Spheraform chart and their default values.

### Global Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.environment` | Environment name (local/staging/production) | `local` |
| `global.storageClass` | Default storage class for PVCs | `standard` |

### PostgreSQL Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `postgres.enabled` | Enable PostgreSQL | `true` |
| `postgres.image.repository` | PostgreSQL image repository | `postgis/postgis` |
| `postgres.image.tag` | PostgreSQL image tag | `16-3.4` |
| `postgres.persistence.size` | PVC size | `2Gi` |
| `postgres.database` | Database name | `spheraform` |
| `postgres.username` | Database username | `spheraform` |
| `postgres.password` | Database password (**change in production!**) | `spheraform_dev` |

### Redis Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `redis.enabled` | Enable Redis | `true` |
| `redis.image.repository` | Redis image repository | `redis` |
| `redis.image.tag` | Redis image tag | `7-alpine` |
| `redis.persistence.size` | PVC size | `1Gi` |
| `redis.appendonly` | Enable AOF persistence | `true` |

### MinIO Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `minio.enabled` | Enable MinIO | `true` |
| `minio.image.repository` | MinIO image repository | `minio/minio` |
| `minio.persistence.size` | PVC size | `1Gi` |
| `minio.rootUser` | MinIO root username | `minioadmin` |
| `minio.rootPassword` | MinIO root password (**change in production!**) | `minioadmin` |
| `minio.bucket` | Default bucket name | `spheraform` |

### Martin (Tile Server) Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `martin.enabled` | Enable Martin tile server | `true` |
| `martin.image.repository` | Martin image repository | `ghcr.io/maplibre/martin` |
| `martin.webuiEnabled` | Enable Martin web UI | `true` |

### API Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `api.enabled` | Enable API service | `true` |
| `api.image.repository` | API image repository | `spheraform-api` |
| `api.image.tag` | API image tag | `latest` |
| `api.replicas` | Number of API replicas | `1` |
| `api.resources.requests.memory` | Memory request | `512Mi` |
| `api.resources.limits.memory` | Memory limit | `2Gi` |

### Web Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `web.enabled` | Enable Web UI | `true` |
| `web.image.repository` | Web image repository | `spheraform-web` |
| `web.image.tag` | Web image tag | `latest` |
| `web.replicas` | Number of Web replicas | `1` |
| `web.env.ORIGIN` | CORS origin | `http://localhost:5173` |

### Ingress Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `nginx` |
| `ingress.hosts` | Ingress hosts configuration | See values.yaml |
| `ingress.tls` | TLS configuration | `[]` |

## Examples

### Override Resource Limits

```bash
helm install spheraform . -f values-local.yaml \
  --set api.resources.limits.memory=4Gi \
  --set postgres.resources.limits.memory=8Gi
```

### Use Custom Storage Class

```bash
helm install spheraform . -f values-production.yaml \
  --set global.storageClass=fast-ssd
```

### Disable Specific Services

```bash
helm install spheraform . -f values-local.yaml \
  --set martin.enabled=false
```

### Enable Ingress with TLS

```yaml
# custom-values.yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: spheraform.example.com
      paths:
        - path: /api
          pathType: Prefix
          backend: api
        - path: /
          pathType: Prefix
          backend: web
  tls:
    - secretName: spheraform-tls
      hosts:
        - spheraform.example.com
```

```bash
helm install spheraform . -f values-production.yaml -f custom-values.yaml
```

## Upgrading

```bash
# Upgrade to new version
helm upgrade spheraform . -f values-production.yaml \
  --set api.image.tag=v0.2.0 \
  --set web.image.tag=v0.2.0
```

## Rollback

```bash
# Rollback to previous release
helm rollback spheraform

# Rollback to specific revision
helm rollback spheraform 2
```

## Accessing Services

### With Port Forwarding (Local/Dev)

```bash
# Web UI
kubectl port-forward svc/spheraform-web 5173:5173

# API
kubectl port-forward svc/spheraform-api 8000:8000

# Martin
kubectl port-forward svc/spheraform-martin 3000:3000

# MinIO Console
kubectl port-forward svc/spheraform-minio 9001:9001
```

### With Ingress (Production)

If ingress is enabled, access via the configured hostname:
- Web UI: `https://spheraform.example.com`
- API: `https://spheraform.example.com/api`

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -l app.kubernetes.io/instance=spheraform
```

### View Logs

```bash
# API logs
kubectl logs -l app.kubernetes.io/component=api -f

# Web logs
kubectl logs -l app.kubernetes.io/component=web -f

# All spheraform logs
kubectl logs -l app.kubernetes.io/instance=spheraform --tail=100 -f
```

### Check PVC Status

```bash
kubectl get pvc -l app.kubernetes.io/instance=spheraform
```

### Database Connection Issues

```bash
# Connect to PostgreSQL
kubectl exec -it deployment/spheraform-postgres -- psql -U spheraform -d spheraform

# Check database connection from API pod
kubectl exec -it deployment/spheraform-api -- env | grep DATABASE_URL
```

### MinIO Access Issues

```bash
# Port-forward to MinIO console
kubectl port-forward svc/spheraform-minio 9001:9001

# Open http://localhost:9001 in browser
# Login with credentials from values file
```

## Security Considerations

1. **Change Default Passwords**: Always override `postgres.password` and `minio.rootPassword` in production
2. **Use Secrets**: Consider using Kubernetes Secrets or external secret managers (e.g., Sealed Secrets, External Secrets Operator)
3. **Enable TLS**: Configure ingress with TLS certificates for production
4. **Network Policies**: Implement network policies to restrict pod-to-pod communication
5. **Resource Limits**: Set appropriate resource requests and limits to prevent resource exhaustion

## License

Apache 2.0
