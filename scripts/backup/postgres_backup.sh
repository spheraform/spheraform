#!/bin/bash
set -euo pipefail

# Spheraform PostgreSQL Backup Script
# Supports: Kubernetes and Docker-Compose
# Features: Dual storage (MinIO + Local), Retention policy, Compression

# ============================================================================
# Configuration
# ============================================================================

# Read from environment or use defaults
BACKUP_ENV="${BACKUP_ENV:-unknown}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-spheraform}"
PGUSER="${PGUSER:-spheraform}"
PGPASSWORD="${PGPASSWORD:-spheraform_dev}"

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
MINIO_BUCKET="${MINIO_BUCKET:-spheraform}"
MINIO_PREFIX="${MINIO_PREFIX:-backups/postgres/}"

RETENTION_HOURLY_HOURS="${RETENTION_HOURLY_HOURS:-72}"
RETENTION_DAILY_DAYS="${RETENTION_DAILY_DAYS:-30}"
RETENTION_DAILY_HOUR="${RETENTION_DAILY_HOUR:-0}"

LOCAL_BACKUP_DIR="/backups/postgres"
BACKUP_TIMESTAMP=$(date +"%Y-%m-%d-%H-%M")
BACKUP_FILENAME="spheraform-backup-${BACKUP_TIMESTAMP}.sql.gz"
TEMP_BACKUP="/tmp/${BACKUP_FILENAME}"

# Export PGPASSWORD for pg_dump
export PGPASSWORD

# ============================================================================
# Logging
# ============================================================================

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

log_error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

# ============================================================================
# Main Backup Function
# ============================================================================

perform_backup() {
    log "Starting PostgreSQL backup for ${PGDATABASE}"
    log "Environment: ${BACKUP_ENV}"

    # Create backup directory
    mkdir -p "${LOCAL_BACKUP_DIR}"

    # Perform pg_dump
    log "Running pg_dump..."
    if ! pg_dump -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" \
         --clean --if-exists --no-owner --no-acl | gzip > "${TEMP_BACKUP}"; then
        log_error "pg_dump failed"
        return 1
    fi

    local backup_size=$(du -h "${TEMP_BACKUP}" | cut -f1)
    log "Backup created: ${BACKUP_FILENAME} (${backup_size})"

    # Upload to MinIO
    upload_to_minio

    # Copy to local storage
    copy_to_local

    # Cleanup temp file
    rm -f "${TEMP_BACKUP}"

    # Run retention cleanup
    cleanup_old_backups

    log "Backup completed successfully"
}

# ============================================================================
# MinIO Upload
# ============================================================================

upload_to_minio() {
    log "Uploading to MinIO: ${MINIO_BUCKET}/${MINIO_PREFIX}${BACKUP_FILENAME}"

    # Configure mc alias
    if ! mc alias set backup "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" --api S3v4 2>/dev/null; then
        log_error "Failed to configure MinIO client"
        return 2
    fi

    # Upload with retry
    local retries=3
    local count=0

    while [ $count -lt $retries ]; do
        if mc cp "${TEMP_BACKUP}" "backup/${MINIO_BUCKET}/${MINIO_PREFIX}${BACKUP_FILENAME}"; then
            log "Successfully uploaded to MinIO"
            return 0
        fi

        count=$((count + 1))
        log "Upload attempt $count failed, retrying..."
        sleep 5
    done

    log_error "Failed to upload to MinIO after ${retries} attempts"
    return 2
}

# ============================================================================
# Local Storage Copy
# ============================================================================

copy_to_local() {
    log "Copying to local storage: ${LOCAL_BACKUP_DIR}/${BACKUP_FILENAME}"

    if ! cp "${TEMP_BACKUP}" "${LOCAL_BACKUP_DIR}/${BACKUP_FILENAME}"; then
        log_error "Failed to copy to local storage"
        return 3
    fi

    log "Successfully copied to local storage"
}

# ============================================================================
# Retention Cleanup
# ============================================================================

cleanup_old_backups() {
    log "Running retention cleanup..."

    local now=$(date +%s)
    local hourly_threshold=$((RETENTION_HOURLY_HOURS * 3600))
    local daily_threshold=$((RETENTION_DAILY_DAYS * 86400))

    # Cleanup MinIO
    cleanup_minio_backups "$now" "$hourly_threshold" "$daily_threshold"

    # Cleanup local storage
    cleanup_local_backups "$now" "$hourly_threshold" "$daily_threshold"

    log "Retention cleanup completed"
}

cleanup_minio_backups() {
    local now=$1
    local hourly_threshold=$2
    local daily_threshold=$3

    log "Cleaning up MinIO backups..."

    # List backups from MinIO
    local backups=$(mc ls "backup/${MINIO_BUCKET}/${MINIO_PREFIX}" 2>/dev/null | awk '{print $NF}' | grep '\.sql\.gz$' || true)

    local kept=0
    local deleted=0

    for filename in $backups; do
        # Extract timestamp from filename
        # Format: spheraform-backup-YYYY-MM-DD-HH-MM.sql.gz
        if [[ $filename =~ spheraform-backup-([0-9]{4})-([0-9]{2})-([0-9]{2})-([0-9]{2})-([0-9]{2})\.sql\.gz ]]; then
            local backup_time=$(date -d "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]} ${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:00" +%s 2>/dev/null || echo 0)

            if [ $backup_time -eq 0 ]; then
                continue
            fi

            local age=$((now - backup_time))
            local backup_hour="${BASH_REMATCH[4]}"

            # Apply retention policy
            if [ $age -le $hourly_threshold ]; then
                # Keep all backups from last 72 hours
                kept=$((kept + 1))
            elif [ $age -le $daily_threshold ]; then
                # Keep daily backups (hour matches RETENTION_DAILY_HOUR)
                # Remove leading zero for comparison
                local hour_num=$((10#${backup_hour}))
                if [ "$hour_num" -eq "$RETENTION_DAILY_HOUR" ]; then
                    kept=$((kept + 1))
                else
                    mc rm "backup/${MINIO_BUCKET}/${MINIO_PREFIX}${filename}" 2>/dev/null || true
                    deleted=$((deleted + 1))
                fi
            else
                # Delete backups older than 30 days
                mc rm "backup/${MINIO_BUCKET}/${MINIO_PREFIX}${filename}" 2>/dev/null || true
                deleted=$((deleted + 1))
            fi
        fi
    done

    log "MinIO cleanup: kept=${kept}, deleted=${deleted}"
}

cleanup_local_backups() {
    local now=$1
    local hourly_threshold=$2
    local daily_threshold=$3

    log "Cleaning up local backups..."

    local kept=0
    local deleted=0

    for backup_file in "${LOCAL_BACKUP_DIR}"/spheraform-backup-*.sql.gz; do
        [ -e "$backup_file" ] || continue

        local filename=$(basename "$backup_file")

        # Extract timestamp
        if [[ $filename =~ spheraform-backup-([0-9]{4})-([0-9]{2})-([0-9]{2})-([0-9]{2})-([0-9]{2})\.sql\.gz ]]; then
            local backup_time=$(date -d "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]} ${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:00" +%s 2>/dev/null || echo 0)

            if [ $backup_time -eq 0 ]; then
                continue
            fi

            local age=$((now - backup_time))
            local backup_hour="${BASH_REMATCH[4]}"

            # Apply retention policy
            if [ $age -le $hourly_threshold ]; then
                kept=$((kept + 1))
            elif [ $age -le $daily_threshold ]; then
                # Remove leading zero for comparison
                local hour_num=$((10#${backup_hour}))
                if [ "$hour_num" -eq "$RETENTION_DAILY_HOUR" ]; then
                    kept=$((kept + 1))
                else
                    rm -f "$backup_file"
                    deleted=$((deleted + 1))
                fi
            else
                rm -f "$backup_file"
                deleted=$((deleted + 1))
            fi
        fi
    done

    log "Local cleanup: kept=${kept}, deleted=${deleted}"
}

# ============================================================================
# Main
# ============================================================================

main() {
    log "========================================="
    log "Spheraform PostgreSQL Backup"
    log "========================================="

    if ! command -v pg_dump &> /dev/null; then
        log_error "pg_dump not found"
        exit 5
    fi

    if ! command -v mc &> /dev/null; then
        log_error "MinIO client (mc) not found"
        exit 5
    fi

    perform_backup
    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        log "Backup process completed successfully"
    else
        log_error "Backup process failed with exit code ${exit_code}"
    fi

    return $exit_code
}

main
exit $?
