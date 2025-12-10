# Utility Scripts

This directory contains utility scripts for development and operations.

## Scripts

### restart-api.sh
Kills any process running on port 8000 and restarts the API service using docker-compose.

```bash
./scripts/restart-api.sh
```

**Use case**: When you need to quickly restart the API during Docker Compose development.

### setup_database.sh
Sets up the database schema and runs migrations.

```bash
./scripts/setup_database.sh
```

**Use case**: Initial database setup or after pulling new migration files.

### test_db_connection.py
Tests PostgreSQL database connectivity using SQLAlchemy.

```bash
python scripts/test_db_connection.py
```

**Environment variables**:
- `DATABASE_URL` - PostgreSQL connection string (default: `postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform`)

**Use case**: Debugging database connection issues.

## Note

These scripts are primarily for **Docker Compose** development. For Kubernetes/DevSpace development, use DevSpace commands instead:

```bash
# Instead of restart-api.sh
devspace dev

# Instead of setup_database.sh
devspace run-pipeline migrate  # (if configured)
```
