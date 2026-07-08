image := "sealman-edge-config-api"
env_file_local := ".env.local"
env_file_docker := ".env.docker"
port := "5000"
hosts := "--add-host keycloak.localhost:host-gateway --add-host sems.localhost:host-gateway"

# List available recipes
default:
    @just --list

# Run locally with uvicorn (hot-reload)
dev:
    uv run uvicorn main:app --host 0.0.0.0 --port {{port}} --env-file {{env_file_local}} --reload

# Build Docker image
build version="local":
    docker build --build-arg VERSION={{version}} -t {{image}}:{{version}} -t {{image}}:latest .

# Run Docker container
run version="latest":
    docker run --rm -p {{port}}:{{port}} --env-file {{env_file_docker}} {{hosts}} {{image}}:{{version}}

# Build and run in one step
up version="local": (build version) (run version)

# Run database migrations manually
migrate:
    uv run alembic upgrade head

# Open a shell inside a running container
shell:
    docker exec -it $(docker ps -qf "ancestor={{image}}") sh

# Stop all running containers for this image
stop:
    docker ps -qf "ancestor={{image}}" | xargs -r docker stop

# Remove the local Docker image
clean:
    docker rmi {{image}}:latest || true
