#!/bin/bash

# Kill all processes on port 8000
echo "Killing processes on port 8000..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || echo "No processes found on port 8000"

# Wait a moment
sleep 1

# Start API with docker-compose
echo "Starting API with docker-compose..."
cd "$(dirname "$0")"
docker-compose up -d api

echo "API started! Check logs with: docker-compose logs -f api"
