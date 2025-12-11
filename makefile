.PHONY: help migrate migrate-pod migrate-create migrate-down migrate-history db-shell api-shell tilt-up tilt-down db-dump-docker db-restore-k8s db-mirror martin-check

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
