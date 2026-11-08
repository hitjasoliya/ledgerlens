#!/bin/bash

# Prevent sourcing the script to protect the user's terminal session
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    echo "Error: run.sh must be executed directly, not sourced."
    return 1 2>/dev/null || exit 1
fi

set -e
# Give each launched job its own process group, including parser/Vite children.
set -m

# Anchor strictly to the script repository directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Visual Header
echo -e "\033[36m==================================================\033[0m"
echo -e "\033[36m      LedgerLens — Microservices Runner          \033[0m"
echo -e "\033[36m==================================================\033[0m"

# 1. Checking Ports (Own only child processes; fail on conflict, never kill unrelated)
echo -e "\033[34m[1/6] Checking ports (8000, 8001, 8002, 8003, 5173)...\033[0m"
ports_conflict=0
for port in 8000 8001 8002 8003 5173; do
    pids=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo -e "\033[31mError: Port $port is already occupied by PID(s): $pids\033[0m"
        ports_conflict=1
    fi
done

if [ $ports_conflict -ne 0 ]; then
    echo -e "\033[31mPort conflict detected. LedgerLens launcher will NOT terminate unrelated processes.\033[0m"
    echo -e "\033[33mTroubleshooting: Stop conflicting processes or configure alternative ports before retrying.\033[0m"
    exit 1
fi
echo "Ports 8000, 8001, 8002, 8003, 5173 are available."

# 2. Docker Compose Detection for Backing Datastores
echo -e "\033[34m[2/6] Checking Docker daemon and starting datastores...\033[0m"
if ! docker info >/dev/null 2>&1; then
    echo -e "\033[33mNotice: Docker daemon is not active. Expecting datastores on configured host ports.\033[0m"
else
    DOCKER_COMPOSE=""
    if docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE="docker compose"
    elif docker-compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE="docker-compose"
    fi

    if [ -n "$DOCKER_COMPOSE" ]; then
        echo "Starting postgres, redis, and elasticsearch using dev compose override..."
        if ! $DOCKER_COMPOSE -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis elasticsearch; then
            echo -e "\033[31mError: Failed to start required Docker datastores.\033[0m"
            exit 1
        fi
    fi
fi

# 3. Environment & Python Setup
echo -e "\033[34m[3/6] Detecting Python and Node environment...\033[0m"
if [ -z "${PYTHON_BIN:-}" ]; then
    PYTHON_BIN="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PYTHON_BIN" ] || ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo -e "\033[31mError: Python executable not found.\033[0m"
    exit 1
fi

if ! "$PYTHON_BIN" -m uvicorn --version >/dev/null 2>&1; then
    echo -e "\033[31mError: uvicorn module not found in $PYTHON_BIN environment.\033[0m"
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo -e "\033[31mError: npm is not installed or not in PATH.\033[0m"
    exit 1
fi

echo "Using Python executable: $PYTHON_BIN"
export PYTHONPATH="$ROOT_DIR/packages/common/src:$ROOT_DIR"

# 4. Database Schema Check (Check current/fresh DB; upgrade requires explicit operator command)
echo -e "\033[34m[4/6] Verifying database schema readiness...\033[0m"
if ! "$PYTHON_BIN" -m common.migrate check; then
    echo -e "\033[31mError: Database schema check failed.\033[0m"
    echo -e "\033[33mNotice: the database uses an older schema. LedgerLens keeps no upgrade path; wipe the database, search index, and uploads, then start again.\033[0m"
    exit 1
fi
echo "Database schema verified."

# 5. Ollama Status Check
echo -e "\033[34m[5/6] Checking Ollama setup...\033[0m"
ollama_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://localhost:11434/api/tags 2>/dev/null || echo "000")
if [ "$ollama_code" = "200" ]; then
    echo "Ollama server is active."
else
    echo -e "\033[33mNotice: Ollama not reachable at http://localhost:11434 (HTTP $ollama_code). Local embeddings require Ollama.\033[0m"
fi

# 6. Launch Microservices and Own Child PIDs
echo -e "\033[34m[6/6] Launching LedgerLens Microservices on private loopback...\033[0m"

CHILD_PIDS=()

cleanup() {
    echo -e "\n\033[33mShutting down launcher-owned processes...\033[0m"
    trap - INT TERM HUP EXIT
    for pid in "${CHILD_PIDS[@]}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done

    # Bounded wait for graceful shutdown (5s)
    for _ in {1..50}; do
        any_alive=0
        for pid in "${CHILD_PIDS[@]}"; do
            if [ -n "$pid" ] && kill -0 -- "-$pid" 2>/dev/null; then
                any_alive=1
                break
            fi
        done
        if [ $any_alive -eq 0 ]; then
            break
        fi
        sleep 0.1
    done

    # Reap only process groups created by these monitored jobs. This also stops
    # descendants when a parent exited before its parser or frontend child.
    for pid in "${CHILD_PIDS[@]}"; do
        if [ -n "$pid" ] && kill -0 -- "-$pid" 2>/dev/null; then
            kill -KILL -- "-$pid" 2>/dev/null || true
        fi
        wait "$pid" 2>/dev/null || true
    done
    echo -e "\033[32mLauncher-owned process groups stopped.\033[0m"
}

trap cleanup INT TERM HUP EXIT

# Launch Identity Service (8001)
"$PYTHON_BIN" -m uvicorn services.identity.main:app --host 127.0.0.1 --port 8001 &
CHILD_PIDS+=($!)

# Launch Ingestion Service (8002)
"$PYTHON_BIN" -m uvicorn services.ingestion.main:app --host 127.0.0.1 --port 8002 &
CHILD_PIDS+=($!)

# Launch RAG Service (8003)
"$PYTHON_BIN" -m uvicorn services.rag.main:app --host 127.0.0.1 --port 8003 &
CHILD_PIDS+=($!)

# Launch Gateway Service (8000)
"$PYTHON_BIN" -m uvicorn services.gateway.main:app --host 127.0.0.1 --port 8000 &
CHILD_PIDS+=($!)

# Launch Frontend (5173)
(cd frontend && exec npm run dev -- --host 127.0.0.1 --port 5173) &
CHILD_PIDS+=($!)

echo -e "\033[32mServices launching! Owned PIDs: ${CHILD_PIDS[*]}\033[0m"
echo -e "\033[32mPress Ctrl+C to stop owned services cleanly.\033[0m"
echo -e "--------------------------------------------------"

# Wait for all owned children
wait
