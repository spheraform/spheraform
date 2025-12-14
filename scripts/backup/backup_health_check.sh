#!/bin/bash
set -euo pipefail

# Backup Health Check Script
# Verifies that recent backups exist in both MinIO and local storage

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
MINIO_BUCKET="${MINIO_BUCKET:-spheraform}"
MINIO_PREFIX="${MINIO_PREFIX:-backups/postgres/}"
LOCAL_BACKUP_DIR="${LOCAL_BACKUP_DIR:-/backups/postgres}"

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
# Health Checks
# ============================================================================

check_minio_backups() {
    log "Checking MinIO backups..."

    # Configure mc alias
    if ! mc alias set backup "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" --api S3v4 2>/dev/null; then
        log_error "Failed to configure MinIO client"
        return 1
    fi

    # Count backups
    local minio_count=$(mc ls "backup/${MINIO_BUCKET}/${MINIO_PREFIX}" 2>/dev/null | grep '\.sql\.gz$' | wc -l || echo 0)
    log "MinIO backups found: ${minio_count}"

    if [ "$minio_count" -eq 0 ]; then
        log_error "No backups found in MinIO"
        return 1
    fi

    return 0
}

check_local_backups() {
    log "Checking local backups..."

    if [ ! -d "$LOCAL_BACKUP_DIR" ]; then
        log_error "Local backup directory does not exist: $LOCAL_BACKUP_DIR"
        return 1
    fi

    local local_count=$(ls -1 "${LOCAL_BACKUP_DIR}"/spheraform-backup-*.sql.gz 2>/dev/null | wc -l || echo 0)
    log "Local backups found: ${local_count}"

    if [ "$local_count" -eq 0 ]; then
        log_error "No backups found in local storage"
        return 1
    fi

    return 0
}

check_recent_backup() {
    log "Checking for recent backup (within last 2 hours)..."

    # Find latest backup
    local latest_backup=$(ls -1t "${LOCAL_BACKUP_DIR}"/spheraform-backup-*.sql.gz 2>/dev/null | head -1 || echo "")

    if [ -z "$latest_backup" ]; then
        log_error "No backups found in local storage"
        return 1
    fi

    # Get backup age
    local backup_mtime=$(stat -c %Y "$latest_backup" 2>/dev/null || stat -f %m "$latest_backup" 2>/dev/null || echo 0)
    local current_time=$(date +%s)
    local backup_age=$((current_time - backup_mtime))
    local backup_age_hours=$((backup_age / 3600))

    log "Latest backup: $(basename "$latest_backup")"
    log "Backup age: ${backup_age_hours} hours"

    if [ $backup_age_hours -gt 2 ]; then
        log_error "WARNING: No backup created in the last 2 hours!"
        log_error "Latest backup is ${backup_age_hours} hours old"
        return 1
    fi

    log "Recent backup check PASSED"
    return 0
}

# ============================================================================
# Main
# ============================================================================

main() {
    log "========================================="
    log "Backup Health Check"
    log "========================================="

    local exit_code=0

    # Check MinIO backups
    if ! check_minio_backups; then
        exit_code=1
    fi

    # Check local backups
    if ! check_local_backups; then
        exit_code=1
    fi

    # Check for recent backup
    if ! check_recent_backup; then
        exit_code=1
    fi

    log "========================================="
    if [ $exit_code -eq 0 ]; then
        log "Backup health check PASSED"
    else
        log_error "Backup health check FAILED"
    fi
    log "========================================="

    return $exit_code
}

main
exit $?
