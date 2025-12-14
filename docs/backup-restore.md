# PostgreSQL Backup and Restore

## Overview

Spheraform automatically backs up the PostgreSQL database every hour with dual redundancy to protect against data loss:

- **MinIO/S3**: Cloud-ready object storage at `s3://spheraform/backups/postgres/`
- **Local Storage**: Persistent volume/disk storage at `/backups/postgres/`

All backups are compressed with gzip for space efficiency and include the full database schema and data.

## Retention Policy

Backups are automatically cleaned up according to this policy:

- **Hourly backups**: Keep ALL backups from the last 72 hours
- **Daily backups**: Keep ONE backup per day (midnight backup) for 72 hours to 30 days old
- **Automatic deletion**: Backups older than 30 days are automatically deleted

Example: If today is January 15th, you'll have:
- All hourly backups from January 12-15 (72 hours)
- One daily backup from each day: January 1-11 (midnight backups only)
- No backups from December or earlier

## Backup Schedule

- **Kubernetes/Tilt**: CronJob runs every hour at minute 0 (00:00, 01:00, 02:00, etc.)
- **docker-compose**: Cron daemon runs every hour at minute 0

## Manual Backup

### Docker-Compose

```bash
make backup-now-docker
```

This runs the backup script immediately in the docker-compose environment.

### Kubernetes/Tilt

```bash
make backup-now-k8s
```

Or use the Tilt UI button: **backup-now**

This creates a one-time Job from the CronJob template.

## List Available Backups

### Docker-Compose

```bash
make backup-list-docker
```

Shows backups in both local storage and MinIO.

### Kubernetes/Tilt

```bash
make backup-list-k8s
```

Shows backups in both the PVC and MinIO.

## Restore from Backup

### Docker-Compose

1. List available backups:
   ```bash
   make backup-list-docker
   ```

2. Choose a backup file and restore:
   ```bash
   make backup-restore-docker FILE=/backups/postgres/spheraform-backup-2024-12-14-10-00.sql.gz
   ```

3. The restore script will:
   - Show backup file size
   - Verify backup integrity
   - Ask for confirmation (type 'yes' to proceed)
   - Drop and recreate all tables
   - Restore data from the backup

### Kubernetes/Tilt

1. Exec into the backup container:
   ```bash
   kubectl exec -it deployment/spheraform-postgres-backup -- /bin/bash
   ```

2. List available backups:
   ```bash
   ls -lh /backups/postgres/
   ```

3. Restore from local backup:
   ```bash
   /scripts/postgres_restore.sh /backups/postgres/spheraform-backup-2024-12-14-10-00.sql.gz
   ```

4. Or restore from MinIO:
   ```bash
   /scripts/postgres_restore.sh backup/spheraform/backups/postgres/spheraform-backup-2024-12-14-10-00.sql.gz
   ```

## Backup Health Check

### Docker-Compose

```bash
make backup-health-docker
```

### Kubernetes/Tilt

```bash
make backup-health-k8s
```

Or use the Tilt UI button: **backup-health**

The health check verifies:
- Backups exist in both MinIO and local storage
- Latest backup is less than 2 hours old
- Exits with error code 1 if any check fails

## Configuration

### Helm Values

Edit `helm/spheraform/values.yaml` to configure backup settings:

```yaml
postgres:
  backup:
    enabled: true
    schedule: "0 * * * *"  # Cron schedule
    retention:
      hourlyBackupHours: 72    # Keep hourly for 72 hours
      dailyBackupDays: 30      # Keep daily for 30 days
      dailyBackupHour: 0       # Which hour to keep as daily (0-23)
    storage:
      local:
        enabled: true
        size: 10Gi             # PVC size
        storageClass: ""       # Uses global.storageClass
      s3:
        enabled: true
        bucket: "spheraform"
        prefix: "backups/postgres/"
```

### Docker-Compose

Edit environment variables in `docker-compose.yml`:

```yaml
postgres-backup:
  environment:
    RETENTION_HOURLY_HOURS: 72
    RETENTION_DAILY_DAYS: 30
    RETENTION_DAILY_HOUR: 0
```

## Backup File Format

Backups are named with timestamp: `spheraform-backup-YYYY-MM-DD-HH-MM.sql.gz`

Example: `spheraform-backup-2024-12-14-15-30.sql.gz`
- Created on December 14, 2024 at 15:30 (3:30 PM)
- Gzip compressed SQL dump
- Includes `--clean --if-exists` flags for safe restore
- Can be restored to any PostgreSQL 16+ database

## Monitoring Backups

### View CronJob Status (Kubernetes)

```bash
kubectl get cronjob spheraform-postgres-backup
```

### View Recent Jobs (Kubernetes)

```bash
kubectl get jobs --selector=app.kubernetes.io/component=postgres-backup
```

### View Backup Logs (Kubernetes)

```bash
# Latest backup job logs
kubectl logs -l app.kubernetes.io/component=postgres-backup --tail=100

# Specific job logs
kubectl logs job/spheraform-postgres-backup-28405220
```

### View Backup Logs (Docker-Compose)

```bash
docker logs spheraform-postgres-backup
```

## Troubleshooting

### No backups are being created (Kubernetes)

1. Check if CronJob exists:
   ```bash
   kubectl get cronjob spheraform-postgres-backup
   ```

2. Check if Jobs are being created:
   ```bash
   kubectl get jobs --selector=app.kubernetes.io/component=postgres-backup
   ```

3. If no jobs, check CronJob schedule:
   ```bash
   kubectl describe cronjob spheraform-postgres-backup
   ```

4. Manually trigger a job to test:
   ```bash
   make backup-now-k8s
   ```

5. Check job logs for errors:
   ```bash
   kubectl logs job/<job-name>
   ```

### No backups are being created (Docker-Compose)

1. Check if backup container is running:
   ```bash
   docker ps | grep postgres-backup
   ```

2. Check container logs:
   ```bash
   docker logs spheraform-postgres-backup
   ```

3. Manually run backup:
   ```bash
   make backup-now-docker
   ```

### Backup job failed

View the error logs:

**Kubernetes**:
```bash
kubectl logs -l app.kubernetes.io/component=postgres-backup --tail=50
```

**Docker-Compose**:
```bash
docker logs spheraform-postgres-backup --tail=50
```

Common errors:
- `pg_dump not found`: PostgreSQL client not installed (should not happen with kartoza/postgis image)
- `MinIO client (mc) not found`: mc binary not in PATH
- `Failed to configure MinIO client`: Check MinIO endpoint and credentials
- `Failed to upload to MinIO`: Check MinIO is running and accessible
- `Failed to copy to local storage`: Check PVC is mounted and writable

### Restore failed

1. Verify backup file exists:
   ```bash
   ls -lh /backups/postgres/spheraform-backup-*.sql.gz
   ```

2. Test backup integrity:
   ```bash
   gunzip -t /backups/postgres/spheraform-backup-2024-12-14-10-00.sql.gz
   ```

3. Check database connectivity:
   ```bash
   psql -h postgres -U spheraform -d spheraform -c "SELECT version();"
   ```

4. Check if PostgreSQL has enough disk space:
   ```bash
   df -h /var/lib/postgresql/data
   ```

### Backups taking too much space

1. Check current backup storage usage:
   ```bash
   # Docker-Compose
   docker exec spheraform-postgres-backup du -sh /backups/postgres/

   # Kubernetes
   kubectl exec deployment/spheraform-postgres-backup -- du -sh /backups/postgres/
   ```

2. Adjust retention policy to keep fewer backups (edit values.yaml or docker-compose.yml)

3. Increase PVC size (Kubernetes only):
   ```yaml
   postgres:
     backup:
       storage:
         local:
           size: 20Gi  # Increase from 10Gi
   ```

## Disaster Recovery

If your entire environment is lost (VM deleted, cluster destroyed), backups in local PVC/volume will also be lost. However, backups in MinIO will survive if MinIO data is on persistent storage.

### Recovery Steps

1. Deploy fresh Spheraform environment
2. Access MinIO to retrieve backups
3. Restore from latest backup

For true disaster recovery:
- Configure MinIO to replicate to external S3 (AWS S3, GCS, etc.)
- Or periodically copy backups to external storage
- Consider database replication for high availability

## Security Considerations

### Backup Encryption

Backups are compressed with gzip but **not encrypted**. For sensitive data:

1. Encrypt backups before uploading:
   ```bash
   gpg --symmetric --cipher-algo AES256 backup.sql.gz
   ```

2. Or configure MinIO server-side encryption

### Access Control

- MinIO bucket has download permissions for the application
- For production, restrict bucket access and use IAM roles
- Consider using Kubernetes Secrets for database credentials instead of plain values

## Best Practices

1. **Test restores regularly**: Don't wait for disaster to test your backups
   ```bash
   # Test restore to a separate database
   createdb test_restore
   gunzip -c backup.sql.gz | psql -d test_restore
   ```

2. **Monitor backup age**: Set up alerts if backups are older than 2 hours
   ```bash
   make backup-health-k8s
   ```

3. **Verify backup integrity**: Check logs for successful backup completion

4. **External backups for production**: Copy critical backups to external storage

5. **Document your restore procedure**: Keep recovery instructions up to date

## FAQ

**Q: Can I change the backup schedule?**

A: Yes, edit the `schedule` in values.yaml (Kubernetes) or the crontab entry in docker-compose.yml.

**Q: Can I disable automatic backups?**

A: Yes, set `postgres.backup.enabled: false` in values.yaml or remove the postgres-backup service from docker-compose.yml.

**Q: How much space do backups use?**

A: Depends on database size. Compressed backups are typically 70-90% smaller than the raw database. A 1GB database will create ~100-300MB compressed backups.

**Q: Can I restore to a different database?**

A: Yes, set the PGDATABASE environment variable when running the restore script.

**Q: What happens if backup fails?**

A: The job/cron will retry on the next scheduled run. Check logs for error details.

**Q: Can I backup specific tables only?**

A: The current implementation backs up the entire database. For selective backups, use `pg_dump` directly with table filters.

**Q: Are backups atomic?**

A: Yes, pg_dump creates a consistent snapshot of the database at the time the backup starts.
