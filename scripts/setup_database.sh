#!/bin/bash

# Setup Spheraform Database Script

echo "🔧 Setting up Spheraform database..."

# Check if SSH tunnel is running on port 5432
if lsof -i :5432 | grep -q ssh; then
    echo "⚠️  SSH tunnel detected on port 5432"
    echo "   You can either:"
    echo "   1. Kill it temporarily: kill \$(lsof -t -i:5432)"
    echo "   2. Or use a different port for Docker"
    echo ""
    read -p "Kill SSH tunnel now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        kill $(lsof -t -i:5432)
        echo "✅ SSH tunnel killed"
        sleep 2
    else
        echo "❌ Cannot proceed with SSH tunnel active"
        exit 1
    fi
fi

# Check if Docker is running
if ! docker ps &> /dev/null; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if postgres container is running
if ! docker ps | grep -q spheraform-postgres; then
    echo "🚀 Starting Docker services..."
    docker-compose up -d
    sleep 5
fi

echo "✅ Docker services running"

# Reset database schema
echo "🗑️  Dropping existing schema..."
docker exec spheraform-postgres psql -U spheraform -d spheraform -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO spheraform;" > /dev/null 2>&1

# Enable PostGIS
echo "🌍 Enabling PostGIS extension..."
docker exec spheraform-postgres psql -U spheraform -d spheraform -c "CREATE EXTENSION IF NOT EXISTS postgis;" > /dev/null 2>&1

# Run migrations
echo "📦 Running database migrations..."
export DATABASE_URL="postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform"
alembic upgrade head

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Database setup complete!"
    echo ""
    echo "📊 Tables created:"
    docker exec spheraform-postgres psql -U spheraform -d spheraform -c "\dt"
    echo ""
    echo "🚀 You can now start the API server:"
    echo "   cd packages/api"
    echo "   uvicorn spheraform_api.main:app --reload --port 8000"
else
    echo ""
    echo "❌ Migration failed. Check the error above."
    exit 1
fi
