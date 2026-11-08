#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null
command -v npm >/dev/null

RESOURCES="$(mktemp -d "${TMPDIR:-/tmp}/ledgerlens-checks.XXXXXXXX")"
trap 'rm -rf "$RESOURCES"' EXIT
export ENV=test
export PYTHONPATH="$ROOT_DIR/packages/common/src:$ROOT_DIR"
export DATABASE_URL="sqlite:///$RESOURCES/bootstrap.sqlite"
export UPLOAD_DIR="$RESOURCES/uploads"
export JWT_SECRET=isolated-test-signing-secret-not-for-deployment
export ADMIN_INITIAL_PASSWORD=isolated-admin-password
export GEMINI_API_KEY=""
export RAG_GENERATOR_ADAPTER=gemini
export ES_HOST=http://127.0.0.1:1
export OLLAMA_HOST=http://127.0.0.1:1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HOME="$RESOURCES/huggingface"
export TORCH_HOME="$RESOURCES/torch"

echo "Checking frontend lint, types, and production bundle..."
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build

# Provision the tokenizer's public, hash-checked vocabulary before pytest
# deliberately disables external provider/network access.
"$PYTHON_BIN" -c 'import tiktoken; tiktoken.get_encoding("cl100k_base")'

echo "Checking concurrent-safe schema initialization in a disposable database..."
"$PYTHON_BIN" -m common.migrate check

echo "Checking all backend behavior regressions with isolated resources..."
"$PYTHON_BIN" -m pytest -q
echo "Isolated quality checks passed. Live providers and container/browser acceptance are separate checks."
