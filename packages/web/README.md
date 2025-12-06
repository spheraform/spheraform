# Spheraform Web Interface

Map-first web interface for Spheraform geospatial data aggregation platform.

## Features

- Full-screen map using MapLibre GL JS
- Floating glassmorphism UI (no top bar)
- Server management and crawling
- Dataset browsing and downloading
- Spatial search with bounding box

## Quick Start

### Development

```bash
# Install dependencies
npm install

# Start dev server
npm run dev
```

Visit http://localhost:5173

### Docker Compose (Recommended)

From project root:

```bash
# Start all services including web interface
docker-compose up -d

# View logs
docker-compose logs -f web
```

Visit http://localhost:5173

### Production Build

```bash
# Build for production
npm run build

# Run production server
export API_URL=http://localhost:8000
node build
```

## Architecture

- **Framework**: SvelteKit with Node adapter
- **Map**: MapLibre GL JS
- **API**: Proxy to FastAPI backend on port 8000
- **UI Style**: Glassmorphism with floating bubbles
- **Deployment**: Docker + Node.js

## Documentation

- [Deployment Guide](./DEPLOYMENT.md) - Docker, production setup, reverse proxy
- [Component Guide](./src/lib/components/) - UI component documentation

## Port Configuration

- **Development**: 5173
- **Production**: 3000 (container internal), mapped to 5173 on host
- **API Backend**: 8000
