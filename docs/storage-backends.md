# Storage Backend Configuration for PMTiles

Spheraform supports multiple storage backends for PMTiles (vector tiles), allowing you to use the storage solution that best fits your infrastructure.

## Supported Storage Backends

Martin tile server supports the following protocols:

| Protocol | Storage Backend | Example |
|----------|----------------|---------|
| `s3://` | AWS S3, MinIO, DigitalOcean Spaces, Cloudflare R2, Ceph | `s3://bucket/datasets/` |
| `gs://` | Google Cloud Storage | `gs://bucket/datasets/` |
| `az://` | Microsoft Azure Blob Storage | `az://account/container/datasets/` |
| `file://` | Local filesystem | `file:///data/datasets/` |
| `https://` | HTTP/HTTPS (CDN, static hosting) | `https://cdn.example.com/datasets/` |

## Configuration

### Environment Variables

Set these in your `.env` file:

```bash
# PMTiles Storage Backend (for Martin tile server)
PMTILES_STORAGE_PROTOCOL=s3://  # Change based on your backend
PMTILES_STORAGE_PATH=spheraform/datasets/
```

### Backend-Specific Setup

#### 1. AWS S3 / MinIO / S3-Compatible Services

**Default configuration** (MinIO for local development):

```bash
PMTILES_STORAGE_PROTOCOL=s3://
PMTILES_STORAGE_PATH=spheraform/datasets/

# S3/MinIO credentials
S3_ENDPOINT=http://localhost:9000  # Omit for AWS S3
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=spheraform
S3_REGION=us-east-1
```

**For AWS S3**:
```bash
PMTILES_STORAGE_PROTOCOL=s3://
PMTILES_STORAGE_PATH=my-bucket/datasets/

S3_ACCESS_KEY=<your-aws-access-key>
S3_SECRET_KEY=<your-aws-secret-key>
S3_BUCKET=my-bucket
S3_REGION=us-east-1
# Do not set S3_ENDPOINT or AWS_S3_FORCE_PATH_STYLE for AWS S3
```

**For DigitalOcean Spaces**:
```bash
PMTILES_STORAGE_PROTOCOL=s3://
PMTILES_STORAGE_PATH=my-space/datasets/

S3_ENDPOINT=https://nyc3.digitaloceanspaces.com
S3_ACCESS_KEY=<your-do-access-key>
S3_SECRET_KEY=<your-do-secret-key>
S3_BUCKET=my-space
S3_REGION=nyc3

# Required for S3-compatible services
AWS_S3_FORCE_PATH_STYLE=true
AWS_ALLOW_HTTP=false  # DigitalOcean Spaces uses HTTPS
```

**For Cloudflare R2**:
```bash
PMTILES_STORAGE_PROTOCOL=s3://
PMTILES_STORAGE_PATH=my-bucket/datasets/

S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
S3_ACCESS_KEY=<your-r2-access-key>
S3_SECRET_KEY=<your-r2-secret-key>
S3_BUCKET=my-bucket
S3_REGION=auto

# Required for S3-compatible services
AWS_S3_FORCE_PATH_STYLE=true
AWS_ALLOW_HTTP=false  # R2 uses HTTPS
```

#### 2. Google Cloud Storage (GCS)

```bash
PMTILES_STORAGE_PROTOCOL=gs://
PMTILES_STORAGE_PATH=my-bucket/datasets/
```

**Authentication**: Martin uses the Google Cloud SDK credentials. Set up authentication:

```bash
# Option 1: Service account key file
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json

# Option 2: Workload Identity (GKE)
# Configure in your Kubernetes service account
```

**Docker-compose**:
```yaml
martin:
  environment:
    GOOGLE_APPLICATION_CREDENTIALS: /secrets/gcs-key.json
  volumes:
    - ./gcs-service-account-key.json:/secrets/gcs-key.json:ro
```

**Kubernetes/Helm**:
```yaml
martin:
  env:
    GOOGLE_APPLICATION_CREDENTIALS: /secrets/gcs-key.json
  # Use Workload Identity or mount secret
```

#### 3. Microsoft Azure Blob Storage

```bash
PMTILES_STORAGE_PROTOCOL=az://
PMTILES_STORAGE_PATH=my-account/my-container/datasets/
```

**Authentication**: Set Azure credentials as environment variables:

```bash
AZURE_STORAGE_ACCOUNT=myaccount
AZURE_STORAGE_KEY=<your-storage-key>
# OR
AZURE_STORAGE_SAS_TOKEN=<your-sas-token>
# OR
AZURE_STORAGE_CONNECTION_STRING=<connection-string>
```

**Docker-compose**:
```yaml
martin:
  environment:
    AZURE_STORAGE_ACCOUNT: myaccount
    AZURE_STORAGE_KEY: ${AZURE_STORAGE_KEY}
```

#### 4. Local Filesystem

Useful for air-gapped deployments or testing without object storage.

```bash
PMTILES_STORAGE_PROTOCOL=file://
PMTILES_STORAGE_PATH=/data/spheraform/datasets/
```

**Docker-compose**:
```yaml
martin:
  volumes:
    - /path/on/host/datasets:/data/spheraform/datasets:ro
```

**Kubernetes**:
```yaml
# Use PersistentVolume or hostPath
martin:
  volumes:
    - name: pmtiles-data
      persistentVolumeClaim:
        claimName: spheraform-pmtiles
```

#### 5. HTTP/HTTPS (CDN or Static Hosting)

Host PMTiles on a CDN or static file server for global distribution.

```bash
PMTILES_STORAGE_PROTOCOL=https://
PMTILES_STORAGE_PATH=cdn.example.com/spheraform/datasets/
```

**Requirements**:
- Files must be publicly accessible or use signed URLs
- Server must support HTTP Range requests (required for PMTiles)

**Example with AWS CloudFront**:
1. Upload PMTiles to S3 bucket
2. Create CloudFront distribution pointing to S3 bucket
3. Configure:
   ```bash
   PMTILES_STORAGE_PROTOCOL=https://
   PMTILES_STORAGE_PATH=d1234567890.cloudfront.net/datasets/
   ```

## Docker-Compose Configuration

The `docker-compose.yml` automatically uses environment variables:

```yaml
martin:
  environment:
    # PMTiles storage backend configuration
    PMTILES_STORAGE_PROTOCOL: ${PMTILES_STORAGE_PROTOCOL:-s3://}
    PMTILES_STORAGE_PATH: ${PMTILES_STORAGE_PATH:-spheraform/datasets/}
```

Set variables in `.env` file, and restart:
```bash
docker-compose restart martin
```

## Kubernetes/Helm Configuration

Update `values.yaml`:

```yaml
martin:
  pmtiles:
    storageProtocol: "s3://"  # or gs://, az://, file://, https://
    storagePath: "spheraform/datasets/"
    cacheSizeMb: 128

  # For S3/MinIO
  env:
    AWS_ACCESS_KEY_ID: "..."
    AWS_SECRET_ACCESS_KEY: "..."
    AWS_ENDPOINT_URL: "http://minio:9000"  # For MinIO
    AWS_REGION: "us-east-1"
    AWS_ALLOW_HTTP: "true"

  # For GCS
  env:
    GOOGLE_APPLICATION_CREDENTIALS: "/secrets/gcs-key.json"

  # For Azure
  env:
    AZURE_STORAGE_ACCOUNT: "myaccount"
    AZURE_STORAGE_KEY: "..."
```

Deploy:
```bash
helm upgrade --install spheraform ./helm/spheraform -f values.yaml
```

## Testing

Verify Martin can access your storage backend:

```bash
# Check Martin logs
docker-compose logs martin

# Or in Kubernetes
kubectl logs deployment/spheraform-martin

# Test tile endpoint
curl http://localhost:3000/catalog
```

You should see PMTiles sources listed in the catalog.

## Performance Considerations

### Caching

Martin caches PMTiles metadata and tiles in memory. Configure cache size based on your dataset size:

```yaml
pmtiles:
  cache_size_mb: 128  # Default
  # Increase for large datasets: 256, 512, 1024
```

### Network Latency

- **S3/MinIO/Local Storage**: Low latency, best for production
- **GCS/Azure**: Moderate latency depending on region
- **HTTP/CDN**: Latency depends on CDN edge location

### Cost

- **Local filesystem**: No storage costs, but requires persistent volumes
- **MinIO**: Self-hosted, storage costs only
- **Cloud object storage**: Pay per GB stored + data transfer
- **CDN**: Additional data transfer costs, but better global performance

## Troubleshooting

### Martin can't access storage

**Error**: `Failed to load PMTiles source`

**Solutions**:
1. Check credentials are set correctly
2. Verify storage path exists and contains `.pmtiles` files
3. Check network connectivity (firewall, security groups)
4. For S3: Verify `AWS_ALLOW_HTTP="true"` for non-HTTPS endpoints
5. For GCS: Verify service account has `storage.objects.get` permission
6. For Azure: Verify SAS token or storage key is valid

### Files not appearing in Martin catalog

**Solutions**:
1. Ensure PMTiles files follow naming convention: `tiles.pmtiles`
2. Check file path pattern in config matches your structure
3. Restart Martin after adding new files
4. Verify file permissions (readable by Martin process)

### HTTP Range request errors

**Error**: `HTTP 416 Range Not Satisfiable`

**Solution**: Your storage backend or proxy doesn't support Range requests. PMTiles requires this. For CDN/proxy, ensure Range request support is enabled.

## Migration Between Backends

To migrate from one storage backend to another:

1. **Copy PMTiles files** to new storage:
   ```bash
   # S3 to GCS
   aws s3 sync s3://old-bucket/datasets/ gs://new-bucket/datasets/

   # Local to S3
   aws s3 sync /data/datasets/ s3://bucket/datasets/
   ```

2. **Update configuration**:
   ```bash
   PMTILES_STORAGE_PROTOCOL=gs://
   PMTILES_STORAGE_PATH=new-bucket/datasets/
   ```

3. **Restart Martin**:
   ```bash
   docker-compose restart martin
   # or
   kubectl rollout restart deployment/spheraform-martin
   ```

4. **Verify** tiles are accessible from new backend

5. **Clean up** old storage after verification

## References

- [Martin Tile Server Documentation](https://maplibre.org/martin/)
- [MBTiles and PMTiles File Sources](https://maplibre.org/martin/sources-files.html)
- [PMTiles Specification](https://github.com/protomaps/PMTiles)
