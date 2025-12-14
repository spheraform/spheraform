#!/bin/bash
set -euo pipefail

# Spheraform PostgreSQL Restore Script

BACKUP_SOURCE="${1:-}"
RESTORE_ENV="${RESTORE_ENV:-docker}"

# Export PGPASSWORD for psql
export PGPASSWORD="${PGPASSWORD:-spheraform_dev}"

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
# Usage
# ============================================================================

usage() {
    echo "Usage: $0 <backup-file-or-s3-path>"
    echo ""
    echo "Examples:"
    echo "  $0 /backups/postgres/spheraform-backup-2024-12-14-10-00.sql.gz"
    echo "  $0 s3://spheraform/backups/postgres/spheraform-backup-2024-12-14-10-00.sql.gz"
    echo ""
    echo "Environment variables:"
    echo "  PGHOST      - PostgreSQL host (default: localhost)"
    echo "  PGPORT      - PostgreSQL port (default: 5432)"
    echo "  PGUSER      - PostgreSQL user (default: spheraform)"
    echo "  PGPASSWORD  - PostgreSQL password (default: spheraform_dev)"
    echo "  PGDATABASE  - PostgreSQL database (default: spheraform)"
    exit 1
}

[ -z "$BACKUP_SOURCE" ] && usage

# ============================================================================
# Main Restore Function
# ============================================================================

main() {
    log "========================================="
    log "Spheraform PostgreSQL Restore"
    log "========================================="

    # Detect if source is S3 or local file
    if [[ "$BACKUP_SOURCE" == s3://* ]] || [[ "$BACKUP_SOURCE" == backup/* ]]; then
        log "Downloading from MinIO..."
        TEMP_FILE="/tmp/restore-backup.sql.gz"

        # If it's an s3:// URL, convert to mc format
        if [[ "$BACKUP_SOURCE" == s3://* ]]; then
            MC_PATH="backup/${BACKUP_SOURCE#s3://}"
        else
            MC_PATH="$BACKUP_SOURCE"
        fi

        if ! mc cp "$MC_PATH" "$TEMP_FILE"; then
            log_error "Failed to download backup from MinIO"
            exit 1
        fi

        BACKUP_FILE="$TEMP_FILE"
    else
        BACKUP_FILE="$BACKUP_SOURCE"
    fi

    if [ ! -f "$BACKUP_FILE" ]; then
        log_error "Backup file not found: $BACKUP_FILE"
        exit 1
    fi

    log "Backup file: $BACKUP_FILE"
    log "Backup size: $(du -h "$BACKUP_FILE" | cut -f1)"

    # Verify backup integrity
    log "Verifying backup integrity..."
    if ! gunzip -t "$BACKUP_FILE" 2>/dev/null; then
        log_error "Backup file is corrupted or not a valid gzip file"
        exit 1
    fi
    log "Backup integrity verified"

    # Database connection details
    local PGHOST="${PGHOST:-localhost}"
    local PGPORT="${PGPORT:-5432}"
    local PGUSER="${PGUSER:-spheraform}"
    local PGDATABASE="${PGDATABASE:-spheraform}"

    log "Database: ${PGDATABASE} at ${PGHOST}:${PGPORT}"
    log ""
    log "WARNING: This will DROP and recreate all tables!"
    log "All existing data will be LOST!"
    log ""

    read -p "Are you sure you want to continue? Type 'yes' to proceed: " confirm

    if [ "$confirm" != "yes" ]; then
        log "Restore cancelled by user"
        exit 0
    fi

    log "Starting restore..."
    log "This may take several minutes depending on backup size..."

    # Perform restore
    if gunzip -c "$BACKUP_FILE" | psql -h "${PGHOST}" \
                                       -p "${PGPORT}" \
                                       -U "${PGUSER}" \
                                       -d "${PGDATABASE}" \
                                       -v ON_ERROR_STOP=1; then
        log "Restore completed successfully"
    else
        log_error "Restore failed"
        exit 1
    fi

    # Cleanup temp file if downloaded from S3
    if [ "${BACKUP_FILE}" = "/tmp/restore-backup.sql.gz" ]; then
        rm -f "$BACKUP_FILE"
        log "Cleaned up temporary files"
    fi

    log "========================================="
    log "Restore process complete"
    log "========================================="
}

main
