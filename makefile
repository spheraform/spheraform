.PHONY: help migrate migrate-pod migrate-create migrate-down migrate-history db-shell api-shell tilt-up tilt-down db-dump-docker db-restore-k8s db-mirror martin-check backup-now-docker backup-now-k8s backup-list-docker backup-list-k8s backup-restore-docker backup-health-docker backup-health-k8s

# Default target
help:
	@echo "Available commands:"
	@echo ""
	@echo "Migrations:"
	@echo "  make migrate              - Run migrations locally"
	@echo "  make migrate-pod          - Run migrations in Kubernetes pod"
	@echo "  make migrate-create MSG=  - Create new migration (requires MSG)"
	@echo "  make migrate-down         - Rollback one migration locally"
	@echo "  make migrate-history      - Show migration history"
	@echo ""
	@echo "Database Management:"
	@echo "  make db-dump-docker       - Dump docker-compose database to backup.sql"
	@echo "  make db-restore-k8s       - Restore backup.sql to Kubernetes database"
	@echo "  make db-mirror            - Mirror docker-compose DB to Kubernetes (dump + restore)"
	@echo "  make db-shell             - Connect to PostgreSQL in pod"
	@echo ""
	@echo "Automated Backups:"
	@echo "  make backup-now-docker    - Run manual backup (docker-compose)"
	@echo "  make backup-now-k8s       - Run manual backup (Kubernetes)"
	@echo "  make backup-list-docker   - List available backups (docker-compose)"
	@echo "  make backup-list-k8s      - List available backups (Kubernetes)"
	@echo "  make backup-restore-docker FILE=<path> - Restore from backup (docker-compose)"
	@echo "  make backup-health-docker - Check backup health (docker-compose)"
	@echo "  make backup-health-k8s    - Check backup health (Kubernetes)"
	@echo ""
	@echo "Debugging:"
	@echo "  make martin-check         - Check Martin tile server status"
	@echo "  make api-shell            - Shell into API pod"
	@echo ""
	@echo "Development:"
	@echo "  make tilt-up              - Start Tilt development environment"
	@echo "  make tilt-down            - Stop Tilt and clean up"

# Database URL for local development
DATABASE_URL ?= postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform

# Run migrations locally
migrate:
	@echo "Running migrations locally..."
	DATABASE_URL=$(DATABASE_URL) alembic upgrade head

# Run migrations in Kubernetes pod
migrate-pod:
	@echo "Running migrations in API pod..."
	kubectl exec deployment/spheraform-api -- alembic upgrade head

# Create a new migration
migrate-create:
	@if [ -z "$(MSG)" ]; then \
		echo "Error: MSG is required. Usage: make migrate-create MSG='your message'"; \
		exit 1; \
	fi
	@echo "Creating migration: $(MSG)"
	DATABASE_URL=$(DATABASE_URL) alembic revision --autogenerate -m "$(MSG)"

# Rollback one migration locally
migrate-down:
	@echo "Rolling back one migration..."
	DATABASE_URL=$(DATABASE_URL) alembic downgrade -1

# Show migration history
migrate-history:
	@echo "Migration history:"
	DATABASE_URL=$(DATABASE_URL) alembic history --verbose

# Connect to PostgreSQL in pod
db-shell:
	@echo "Connecting to PostgreSQL..."
	kubectl exec -it deployment/spheraform-postgres -- psql -U spheraform -d spheraform

# Shell into API pod
api-shell:
	@echo "Opening shell in API pod..."
	kubectl exec -it deployment/spheraform-api -- /bin/bash

# Check Martin tile server status
martin-check:
	@echo "Checking Martin tile server..."
	@echo ""
	@echo "1. Pod status:"
	@kubectl get pods -l app.kubernetes.io/component=martin
	@echo ""
	@echo "2. Available tile sources:"
	@curl -s "http://localhost:3000/catalog" | jq -r '.tiles | keys[]' | grep cache_ | head -10
	@echo "   ... (run 'curl http://localhost:3000/catalog | jq' for full list)"
	@echo ""
	@echo "3. Martin web UI: http://localhost:3000/"
	@echo ""

# Start Tilt
tilt-up:
	@echo "Starting Tilt..."
	tilt up

# Stop Tilt and clean up
tilt-down:
	@echo "Stopping Tilt..."
	tilt down

# Dump docker-compose database to file
db-dump-docker:
	@echo "Dumping docker-compose database to backup.sql..."
	@docker exec -t spheraform-postgres pg_dump -U spheraform -d spheraform --clean --if-exists > backup.sql
	@echo "Backup saved to backup.sql ($(shell wc -l < backup.sql | tr -d ' ') lines)"

# Restore backup to Kubernetes database
db-restore-k8s:
	@if [ ! -f backup.sql ]; then \
		echo "Error: backup.sql not found. Run 'make db-dump-docker' first."; \
		exit 1; \
	fi
	@echo "Restoring backup.sql to Kubernetes database..."
	@cat backup.sql | kubectl exec -i deployment/spheraform-postgres -- psql -U spheraform -d spheraform
	@echo "Restore complete!"

# Mirror docker-compose database to Kubernetes (dump + restore)
db-mirror:
	@echo "Mirroring docker-compose database to Kubernetes..."
	@echo ""
	@echo "Step 1: Dumping from docker-compose..."
	@docker exec -t spheraform-postgres pg_dump -U spheraform -d spheraform --clean --if-exists > backup.sql
	@echo "✓ Backup saved to backup.sql ($(shell wc -l < backup.sql | tr -d ' ') lines)"
	@echo ""
	@echo "Step 2: Restoring to Kubernetes..."
	@cat backup.sql | kubectl exec -i deployment/spheraform-postgres -- psql -U spheraform -d spheraform
	@echo ""
	@echo "✓ Database mirrored successfully!"
	@echo ""
	@echo "Cleaning up..."
	@rm -f backup.sql
	@echo "✓ Temporary backup.sql removed"

# ============================================================================
# Automated Backup Commands
# ============================================================================

# Run manual backup in docker-compose
backup-now-docker:
	@echo "Running manual backup (docker-compose)..."
	@docker exec spheraform-postgres-backup /scripts/postgres_backup.sh

# Run manual backup in Kubernetes
backup-now-k8s:
	@echo "Running manual backup (Kubernetes)..."
	@kubectl create job --from=cronjob/spheraform-postgres-backup manual-backup-$(shell date +%s)
	@echo "Job created. Check status with: kubectl get jobs"
	@echo "View logs with: kubectl logs -l app.kubernetes.io/component=postgres-backup"

# List backups in docker-compose
backup-list-docker:
	@echo "=== Local Backups ==="
	@docker exec spheraform-postgres-backup ls -lh /backups/postgres/ 2>/dev/null || echo "No backups found"
	@echo ""
	@echo "=== MinIO Backups ==="
	@docker exec spheraform-postgres-backup mc ls backup/spheraform/backups/postgres/ 2>/dev/null || echo "No backups found"

# List backups in Kubernetes
backup-list-k8s:
	@echo "=== MinIO Backups ==="
	@kubectl exec deployment/spheraform-minio -- mc ls local/spheraform/backups/postgres/ 2>/dev/null || echo "No backups found"
	@echo ""
	@echo "Note: To list local PVC backups, create a temporary pod with the backup PVC mounted"

# Restore backup in docker-compose
backup-restore-docker:
	@if [ -z "$(FILE)" ]; then \
		echo "Error: FILE is required. Usage: make backup-restore-docker FILE=<backup-file>"; \
		echo ""; \
		echo "Example:"; \
		echo "  make backup-restore-docker FILE=/backups/postgres/spheraform-backup-2024-12-14-10-00.sql.gz"; \
		echo ""; \
		echo "List available backups with: make backup-list-docker"; \
		exit 1; \
	fi
	@echo "Restoring backup: $(FILE)"
	@docker exec -i spheraform-postgres-backup /scripts/postgres_restore.sh $(FILE)

# Check backup health in docker-compose
backup-health-docker:
	@echo "Checking backup health (docker-compose)..."
	@docker exec spheraform-postgres-backup /scripts/backup_health_check.sh

# Check backup health in Kubernetes
backup-health-k8s:
	@echo "Checking backup health (Kubernetes)..."
	@echo "Checking MinIO backups..."
	@BACKUP_COUNT=$$(kubectl exec deployment/spheraform-minio -- mc ls local/spheraform/backups/postgres/ 2>/dev/null | wc -l) && \
	echo "Found $$BACKUP_COUNT backups in MinIO" && \
	if [ $$BACKUP_COUNT -gt 0 ]; then \
		LATEST=$$(kubectl exec deployment/spheraform-minio -- mc ls local/spheraform/backups/postgres/ 2>/dev/null | tail -1 | awk '{print $$4}'); \
		echo "Latest backup: $$LATEST"; \
		echo "✓ Backup health check PASSED"; \
	else \
		echo "✗ No backups found"; \
		exit 1; \
	fi
