#!/usr/bin/env bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    Spheraform Kubernetes Rebuild                         ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════════════╝${NC}"

# Check if Kubernetes context is allowed
CURRENT_CONTEXT=$(kubectl config current-context)
echo -e "${BLUE}→${NC} Current Kubernetes context: ${YELLOW}${CURRENT_CONTEXT}${NC}"

if [[ "$CURRENT_CONTEXT" != "minikube" && "$CURRENT_CONTEXT" != "docker-desktop" && "$CURRENT_CONTEXT" != "kind" ]]; then
    echo -e "${RED}✗${NC} Context '$CURRENT_CONTEXT' is not allowed for local development"
    echo -e "${YELLOW}  Allowed contexts: minikube, docker-desktop, kind${NC}"
    exit 1
fi

# Function to check if using minikube
using_minikube() {
    [[ "$CURRENT_CONTEXT" == "minikube" ]]
}

# Function to check if using kind
using_kind() {
    [[ "$CURRENT_CONTEXT" == "kind" ]]
}

echo ""
echo -e "${GREEN}[1/6]${NC} Building Docker images..."
echo -e "${BLUE}──────────────────────────────────────────────────────────────────────────${NC}"

# Set Docker environment for minikube if needed
if using_minikube; then
    echo -e "${BLUE}→${NC} Using minikube Docker daemon"
    eval $(minikube -p minikube docker-env)
fi

# Build API image
echo -e "${YELLOW}→${NC} Building spheraform-api:latest..."
docker build \
    -t spheraform-api:latest \
    -f packages/api/Dockerfile \
    --progress=plain \
    . 2>&1 | grep -E "^#|^Step|^Successfully|ERROR|WARN" || true

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo -e "${RED}✗${NC} API build failed"
    exit 1
fi
echo -e "${GREEN}✓${NC} API image built successfully"

# Build Web image
echo -e "${YELLOW}→${NC} Building spheraform-web:latest..."
docker build \
    -t spheraform-web:latest \
    -f packages/web/Dockerfile \
    --progress=plain \
    . 2>&1 | grep -E "^#|^Step|^Successfully|ERROR|WARN" || true

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo -e "${RED}✗${NC} Web build failed"
    exit 1
fi
echo -e "${GREEN}✓${NC} Web image built successfully"

# Load images into kind if using kind
if using_kind; then
    echo ""
    echo -e "${GREEN}[2/6]${NC} Loading images into kind cluster..."
    echo -e "${BLUE}──────────────────────────────────────────────────────────────────────────${NC}"

    echo -e "${YELLOW}→${NC} Loading spheraform-api:latest..."
    kind load docker-image spheraform-api:latest

    echo -e "${YELLOW}→${NC} Loading spheraform-web:latest..."
    kind load docker-image spheraform-web:latest

    echo -e "${GREEN}✓${NC} Images loaded into kind"
else
    echo ""
    echo -e "${GREEN}[2/6]${NC} Skipping image load (not using kind)"
fi

echo ""
echo -e "${GREEN}[3/6]${NC} Verifying images are available..."
echo -e "${BLUE}──────────────────────────────────────────────────────────────────────────${NC}"

if using_minikube; then
    eval $(minikube -p minikube docker-env)
fi

if docker images spheraform-api:latest | grep -q "spheraform-api"; then
    echo -e "${GREEN}✓${NC} spheraform-api:latest found"
else
    echo -e "${RED}✗${NC} spheraform-api:latest not found"
    exit 1
fi

if docker images spheraform-web:latest | grep -q "spheraform-web"; then
    echo -e "${GREEN}✓${NC} spheraform-web:latest found"
else
    echo -e "${RED}✗${NC} spheraform-web:latest not found"
    exit 1
fi

echo ""
echo -e "${GREEN}[4/6]${NC} Restarting deployments..."
echo -e "${BLUE}──────────────────────────────────────────────────────────────────────────${NC}"

# Delete pods to force image pull
echo -e "${YELLOW}→${NC} Deleting API pods..."
kubectl delete pods -l app=spheraform-api 2>/dev/null || echo -e "${YELLOW}  No API pods to delete${NC}"

echo -e "${YELLOW}→${NC} Deleting Web pods..."
kubectl delete pods -l app=spheraform-web 2>/dev/null || echo -e "${YELLOW}  No Web pods to delete${NC}"

echo -e "${YELLOW}→${NC} Deleting Celery download worker pods..."
kubectl delete pods -l app=spheraform-celery-download 2>/dev/null || echo -e "${YELLOW}  No Celery download pods to delete${NC}"

echo -e "${YELLOW}→${NC} Deleting Celery crawl worker pods..."
kubectl delete pods -l app=spheraform-celery-crawl 2>/dev/null || echo -e "${YELLOW}  No Celery crawl pods to delete${NC}"

echo ""
echo -e "${GREEN}[5/6]${NC} Waiting for deployments to be ready..."
echo -e "${BLUE}──────────────────────────────────────────────────────────────────────────${NC}"

# Wait for API
echo -e "${YELLOW}→${NC} Waiting for spheraform-api..."
kubectl wait --for=condition=available --timeout=180s deployment/spheraform-api 2>/dev/null || {
    echo -e "${YELLOW}  Warning: spheraform-api deployment not found or not ready yet${NC}"
}

# Wait for Web
echo -e "${YELLOW}→${NC} Waiting for spheraform-web..."
kubectl wait --for=condition=available --timeout=180s deployment/spheraform-web 2>/dev/null || {
    echo -e "${YELLOW}  Warning: spheraform-web deployment not found or not ready yet${NC}"
}

echo -e "${GREEN}✓${NC} Deployments ready"

echo ""
echo -e "${GREEN}[6/6]${NC} Checking pod status..."
echo -e "${BLUE}──────────────────────────────────────────────────────────────────────────${NC}"

# Show pod status
kubectl get pods -l 'app in (spheraform-api,spheraform-web,spheraform-celery-download,spheraform-celery-crawl)' \
    -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount,AGE:.metadata.creationTimestamp 2>/dev/null || {
    echo -e "${YELLOW}No pods found yet${NC}"
}

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                             Rebuild Complete!                            ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Services are accessible at:${NC}"
echo -e "  • Web UI:      ${BLUE}http://localhost:5173${NC}"
echo -e "  • API Docs:    ${BLUE}http://localhost:8000/docs${NC}"
echo -e "  • Martin:      ${BLUE}http://localhost:3000${NC}"
echo -e "  • MinIO:       ${BLUE}http://localhost:9001${NC} (minioadmin/minioadmin)"
echo -e "  • Flower:      ${BLUE}http://localhost:5555${NC}"
echo ""
echo -e "${YELLOW}Troubleshooting:${NC}"
echo -e "  • Check logs:  ${BLUE}kubectl logs -f deployment/spheraform-api${NC}"
echo -e "  • Check web:   ${BLUE}kubectl logs -f deployment/spheraform-web${NC}"
echo -e "  • List pods:   ${BLUE}kubectl get pods${NC}"
echo ""
echo -e "${YELLOW}CORS Testing:${NC}"
echo -e "  • Check MinIO CORS: ${BLUE}kubectl logs deployment/spheraform-minio | grep -i cors${NC}"
echo -e "  • Test PMTiles access: ${BLUE}curl -I http://localhost:9000/spheraform/datasets/<dataset-id>/tiles.pmtiles${NC}"
echo -e "  • Check browser console for CORS errors"
echo ""
