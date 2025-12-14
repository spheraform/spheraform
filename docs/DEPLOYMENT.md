# Deployment Guide

## Docker Compose Deployment

The web interface is configured to run in Docker Compose alongside the API and other services.

### Starting All Services

From the project root:

```bash
# Build and start all services
docker-compose up -d

# Or build web service only
docker-compose up -d web
```

### Service Configuration

- **Web Interface**: http://localhost:5173
- **API Backend**: http://localhost:8000
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **MinIO**: http://localhost:9001 (console)
- **Martin Tiles**: http://localhost:3000

### Environment Variables

The web service uses:
- `API_URL`: Backend API URL (default: http://api:8000)
- `ORIGIN`: Allowed origin for CORS (default: http://localhost:5173)

### Updating the Web Interface

After making changes to the code:

```bash
# Rebuild and restart the web service
docker-compose up -d --build web

# View logs
docker-compose logs -f web
```

## Production Deployment

### Build for Production

```bash
cd packages/web
npm run build
```

### Run Production Build

```bash
# Set environment variables
export API_URL=https://your-api-domain.com
export ORIGIN=https://your-domain.com

# Start the server
node build
```

The production server listens on port 3000 by default.

### Docker Production

The Dockerfile uses multi-stage builds:
1. **Builder stage**: Installs dependencies and builds the app
2. **Production stage**: Only includes built files and production dependencies

### Reverse Proxy Setup

For production, use a reverse proxy (nginx, Caddy, Traefik) to:
- Serve the web interface on port 443/80
- Handle SSL/TLS termination
- Proxy /api requests to the backend API

Example nginx configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## Development Mode

For local development:

```bash
cd packages/web
npm run dev
```

This starts Vite dev server with hot reload on http://localhost:5173
