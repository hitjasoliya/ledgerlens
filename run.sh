#!/bin/bash

# Prevent sourcing the script to protect the user's terminal session
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    echo -e "\033[31mError: This script must be executed, not sourced. Run it as:\033[0m"
    echo "  ./run.sh"
    return 1 2>/dev/null || exit 1
fi

# Visual Header
echo -e "\033[36m==================================================\033[0m"
echo -e "\033[36m      LedgerLens — Microservices Runner          \033[0m"
echo -e "\033[36m==================================================\033[0m"

# 1. Freeing & Checking Ports
echo -e "\033[34m[1/5] Freeing ports (8000, 8001, 8002, 8003, 5173)...\033[0m"
for port in 8000 8001 8002 8003 5173; do
    pids=$(lsof -ti :$port 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "\033[33mFreeing port $port (killing PID(s): $pids)...\033[0m"
        kill -9 $pids 2>/dev/null || true
        sleep 0.5
    fi
done
echo "Ports 8000, 8001, 8002, 8003, 5173 are free."

# 2. Docker Compose Detection
echo -e "\033[34m[2/5] Checking Docker daemon and starting databases...\033[0m"
if ! docker info >/dev/null 2>&1; then
    echo -e "\033[33mWarning: Docker daemon is not running. Launching local fallback mode.\033[0m"
else
    # Detect docker-compose command
    if docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE="docker compose"
    elif docker-compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE="docker-compose"
    fi

    if [ -n "$DOCKER_COMPOSE" ]; then
        # Spin up postgres, redis, elasticsearch database services
        $DOCKER_COMPOSE up -d postgres redis elasticsearch 2>/dev/null || true
    fi
fi

# 3. Environment & Python Setup
echo -e "\033[34m[3/5] Detecting Python and Node environment...\033[0m"
PYTHON_ENV="$(which python3)"
UVICORN_ENV="$(which uvicorn 2>/dev/null || echo "uvicorn")"

if [ -f "/opt/miniconda3/bin/uvicorn" ]; then
    UVICORN_ENV="/opt/miniconda3/bin/uvicorn"
fi

echo "Using Python executable: $PYTHON_ENV"
echo "Using Uvicorn executable: $UVICORN_ENV"

# Verify node/npm
if ! command -v npm >/dev/null 2>&1; then
    echo -e "\033[31mError: Node.js and npm are not installed.\033[0m"
    exit 1
fi
echo "Node/NPM environment is ready."

# 4. Ollama Check
echo -e "\033[34m[4/5] Checking Ollama setup...\033[0m"
if curl -s -o /dev/null -w "%{http_code}" http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama is running on http://localhost:11434."
else
    echo -e "\033[33mWarning: Ollama is not running. Hash fallback embeddings will be used.\033[0m"
fi

# 5. Concurrent Microservices Launch
echo -e "\033[34m[5/5] Launching LedgerLens Microservices...\033[0m"
echo -e "\033[32mServices starting! Press Ctrl+C to stop all services.\033[0m"
echo -e "--------------------------------------------------"

cleanup() {
    echo -e "\n\033[33mShutting down all services...\033[0m"
    trap - INT TERM HUP
    for port in 8000 8001 8002 8003 5173; do
        pids=$(lsof -ti :$port 2>/dev/null)
        if [ -n "$pids" ]; then
            kill -9 $pids 2>/dev/null || true
        fi
    done
    exit 0
}
trap cleanup INT TERM HUP

ROOT_DIR="$(pwd)"
export PYTHONPATH="$ROOT_DIR/packages/common/src:$ROOT_DIR"

# Start Identity Service (8001)
($UVICORN_ENV services.identity.main:app --port 8001) 2>&1 | while read -r line; do
    echo -e "\033[33m[Identity :8001]\033[0m $line"
done &

# Start Ingestion Service (8002)
($UVICORN_ENV services.ingestion.main:app --port 8002) 2>&1 | while read -r line; do
    echo -e "\033[34m[Ingestion :8002]\033[0m $line"
done &

# Start RAG Service (8003)
($UVICORN_ENV services.rag.main:app --port 8003) 2>&1 | while read -r line; do
    echo -e "\033[35m[RAG :8003]\033[0m $line"
done &

# Start Gateway Service (8000)
($UVICORN_ENV services.gateway.main:app --port 8000) 2>&1 | while read -r line; do
    echo -e "\033[36m[Gateway :8000]\033[0m $line"
done &

# Start Frontend (5173)
(cd frontend && exec npm run dev) 2>&1 | while read -r line; do
    echo -e "\033[32m[Frontend :5173]\033[0m $line"
done &

wait
