.PHONY: help migrate migrate-pod migrate-create migrate-down migrate-history db-shell api-shell tilt-up tilt-down

# Default target
help:
	@echo "Available commands:"
	@echo "  make migrate              - Run migrations locally"
	@echo "  make migrate-pod          - Run migrations in Kubernetes pod"
	@echo "  make migrate-create MSG=  - Create new migration (requires MSG)"
	@echo "  make migrate-down         - Rollback one migration locally"
	@echo "  make migrate-history      - Show migration history"
	@echo "  make db-shell             - Connect to PostgreSQL in pod"
	@echo "  make api-shell            - Shell into API pod"
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

# Start Tilt
tilt-up:
	@echo "Starting Tilt..."
	tilt up

# Stop Tilt and clean up
tilt-down:
	@echo "Stopping Tilt..."
	tilt down
