#!/bin/bash

# Prevent sourcing the script to protect the user's terminal session
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    echo -e "\033[31mError: This script must be executed, not sourced. Run it as:\033[0m"
    echo "  ./run.sh"
    return 1 2>/dev/null || exit 1
fi

# Visual Header
echo -e "\033[36m==================================================\033[0m"
echo -e "\033[36m      CapitalQuery — Unified Project Runner       \033[0m"
echo -e "\033[36m==================================================\033[0m"

# 1. Port Checks
echo -e "\033[34m[1/5] Checking ports availability...\033[0m"
if lsof -i :8000 -t >/dev/null 2>&1; then
    echo -e "\033[31mError: Port 8000 (Backend) is already in use.\033[0m"
    echo "Please stop the process running on port 8000 and try again."
    exit 1
fi
if lsof -i :5173 -t >/dev/null 2>&1; then
    echo -e "\033[31mError: Port 5173 (Frontend) is already in use.\033[0m"
    echo "Please stop the process running on port 5173 and try again."
    exit 1
fi
echo "Ports 8000 and 5173 are free."

# 2. Docker Compose Detection
echo -e "\033[34m[2/5] Checking Docker daemon and starting databases...\033[0m"
if ! docker info >/dev/null 2>&1; then
    echo -e "\033[31mError: Docker daemon is not running.\033[0m"
    echo "Please start Docker Desktop on your Mac and try again."
    exit 1
fi

# Detect docker-compose command
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif docker-compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    echo -e "\033[31mError: Neither 'docker compose' nor 'docker-compose' could be found.\033[0m"
    exit 1
fi

# Spin up database services
$DOCKER_COMPOSE up -d

# Wait for databases health status
echo -n "Waiting for databases (Elasticsearch & PostgreSQL) to be healthy..."
while true; do
    ES_STATUS=$(docker inspect --format='{{json .State.Health.Status}}' rag_elasticsearch 2>/dev/null | tr -d '"')
    PG_STATUS=$(docker inspect --format='{{json .State.Health.Status}}' rag_postgres 2>/dev/null | tr -d '"')
    
    if [ "$ES_STATUS" = "healthy" ] && [ "$PG_STATUS" = "healthy" ]; then
        break
    fi
    echo -n "."
    sleep 2
done
echo -e "\n\033[32mDatabases are healthy and ready!\033[0m"

# 3. Environment & Python Setup
echo -e "\033[34m[3/5] Detecting Python and Node environment...\033[0m"
PYTHON_ENV="/opt/miniconda3/envs/kingslayer/bin/python"
UVICORN_ENV="/opt/miniconda3/envs/kingslayer/bin/uvicorn"

if [ -f "$PYTHON_ENV" ] && [ -f "$UVICORN_ENV" ]; then
    echo "Using kingslayer Conda environment from: $PYTHON_ENV"
else
    # Fallback checks
    if conda info --envs | grep -q "kingslayer" 2>/dev/null; then
        PYTHON_ENV="conda run -n kingslayer python"
        UVICORN_ENV="conda run -n kingslayer uvicorn"
        echo "Using kingslayer via conda run"
    else
        PYTHON_ENV="python3"
        UVICORN_ENV="uvicorn"
        echo -e "\033[33mWarning: 'kingslayer' Conda environment not found. Falling back to system python3.\033[0m"
    fi
fi

# Verify node/npm
if ! command -v npm >/dev/null 2>&1; then
    echo -e "\033[31mError: Node.js and npm are not installed.\033[0m"
    exit 1
fi
echo "Node/NPM environment is ready."

# 4. Ollama Check
echo -e "\033[34m[4/5] Checking Ollama setup...\033[0m"
if curl -s -o /dev/null -w "%{http_code}" http://localhost:11434/api/tags >/dev/null 2>&1; then
    if curl -s http://localhost:11434/api/tags | grep -q "embeddinggemma"; then
        echo "Ollama is running with 'embeddinggemma' model."
    else
        echo -e "\033[33mWarning: Ollama is running, but 'embeddinggemma' model was not found.\033[0m"
        echo "Please run: ollama pull embeddinggemma"
    fi
else
    echo -e "\033[33mWarning: Ollama is not running on http://localhost:11434.\033[0m"
    echo "Please launch Ollama and pull 'embeddinggemma' to use local vector search."
fi

# 5. Concurrent Servers Launch
echo -e "\033[34m[5/5] Launching Backend and Frontend servers...\033[0m"
echo -e "\033[32mServers started! Press Ctrl+C to stop all services.\033[0m"
echo -e "--------------------------------------------------"

# Define cleanup function to kill entire process tree on interrupt
cleanup() {
    echo -e "\n\033[33mShutting down all processes...\033[0m"
    trap - EXIT INT TERM
    kill -TERM -$$ 2>/dev/null
    exit 0
}
trap cleanup EXIT INT TERM

# Start Backend with Cyan colorized logs
(cd backend && exec $UVICORN_ENV app.main:app --port 8000) 2>&1 | while read -r line; do
    echo -e "\033[36m[Backend]\033[0m $line"
done &

# Start Frontend with Magenta colorized logs
(cd frontend && exec npm run dev) 2>&1 | while read -r line; do
    echo -e "\033[35m[Frontend]\033[0m $line"
done &

# Wait on background processes
wait
