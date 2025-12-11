# Tiltfile - Fast local development with Helm
# Enable Kubernetes
allow_k8s_contexts(['minikube', 'docker-desktop', 'kind'])

# Load environment variables
load('ext://dotenv', 'dotenv')
dotenv()

# Configuration
HELM_CHART = './helm/spheraform'
VALUES_FILE = './helm/spheraform/values-local.yaml'

# Build Docker images with live update
docker_build(
    'spheraform-api',
    context='.',
    dockerfile='./packages/api/Dockerfile',
    live_update=[
        sync('./packages/api', '/app/api'),
        sync('./packages/core', '/app/core'),
        run('pip install -e /app/core', trigger=['./packages/core/pyproject.toml']),
        run('pip install -e /app/api', trigger=['./packages/api/pyproject.toml']),
    ],
    ignore=['__pycache__', '.pytest_cache', '**/*.pyc'],
)

docker_build(
    'spheraform-web',
    context='.',
    dockerfile='./packages/web/Dockerfile',
    live_update=[
        sync('./packages/web/src', '/app/src'),
        sync('./packages/web/static', '/app/static'),
        run('npm install', trigger=['./packages/web/package.json']),
    ],
    ignore=['node_modules', 'dist', '.svelte-kit'],
)

# Deploy using Helm
k8s_yaml(
    helm(
        HELM_CHART,
        name='spheraform',
        namespace='default',
        values=[VALUES_FILE],
        set=[
            'api.image.pullPolicy=Never',
            'web.image.pullPolicy=Never',
            'api.image.tag=latest',
            'web.image.tag=latest',
            'martin.image.pullPolicy=IfNotPresent',
        ]
    )
)

# Resource configuration with port forwarding
k8s_resource(
    'spheraform-api',
    port_forwards='8000:8000',
    labels=['services'],
    resource_deps=['spheraform-postgres', 'spheraform-redis', 'spheraform-minio'],
)

k8s_resource(
    'spheraform-web',
    port_forwards='5173:3000',
    labels=['services'],
    resource_deps=['spheraform-api'],
)

k8s_resource(
    'spheraform-martin',
    port_forwards='3000:3000',
    labels=['services'],
    resource_deps=['spheraform-postgres'],
)

k8s_resource(
    'spheraform-postgres',
    port_forwards='5432:5432',
    labels=['databases'],
)

k8s_resource(
    'spheraform-redis',
    port_forwards='6379:6379',
    labels=['databases'],
)

k8s_resource(
    'spheraform-minio',
    port_forwards=['9000:9000', '9001:9001'],
    labels=['storage'],
)

k8s_resource(
    'spheraform-minio-setup',
    labels=['storage'],
)

# Custom buttons for Tilt UI
local_resource(
    'helm-lint',
    cmd='helm lint ' + HELM_CHART,
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
    labels=['tools'],
)

local_resource(
    'db-shell',
    cmd='kubectl exec -it deployment/spheraform-postgres -- psql -U spheraform -d spheraform',
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
    resource_deps=['spheraform-postgres'],
    labels=['tools'],
)

local_resource(
    'redis-cli',
    cmd='kubectl exec -it deployment/spheraform-redis -- redis-cli',
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
    resource_deps=['spheraform-redis'],
    labels=['tools'],
)

local_resource(
    'api-logs',
    cmd='kubectl logs -f deployment/spheraform-api',
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
    resource_deps=['spheraform-api'],
    labels=['tools'],
)

# Watch for changes to Helm chart
watch_file(HELM_CHART + '/values.yaml')
watch_file(VALUES_FILE)
watch_file(HELM_CHART + '/templates/**/*.yaml')

# Watch application files
watch_file('packages/api/**/*.py')
watch_file('packages/web/**/*.{js,ts,jsx,tsx,svelte}')

print("""
╔══════════════════════════════════════════════════════════════════════════╗
║                           Spheraform Development                          ║
╚══════════════════════════════════════════════════════════════════════════╝

Services:
  • Web UI:      http://localhost:5173
  • API:         http://localhost:8000/docs
  • Martin:      http://localhost:3000
  • MinIO:       http://localhost:9001 (minioadmin/minioadmin)
  • PostgreSQL:  localhost:5432
  • Redis:       localhost:6379

Press 'space' to open Tilt UI

Custom Commands:
  • helm-lint  - Validate Helm chart
  • db-shell   - Connect to PostgreSQL
  • redis-cli  - Connect to Redis
  • api-logs   - Stream API logs
""")
