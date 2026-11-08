"""Keep every pytest invocation away from workstation data and live providers."""
import os
import sys
import tempfile
from pathlib import Path

_project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_root / "packages/common/src"))
sys.path.insert(0, str(_project_root))

from services.gateway.tests.redis_harness import (  # noqa: E402
    RedisServer,
    find_redis_binary,
    start_redis_server,
)

_test_resources = tempfile.TemporaryDirectory(prefix="ledgerlens-tests-")
_test_root = Path(_test_resources.name)
_root_redis = start_redis_server(
    data_dir=_test_root / "redis", prefix="ledgerlens-root-redis-"
)

os.environ.update(
    ENV="test",
    DATABASE_URL=f"sqlite:///{_test_root / 'unit.sqlite'}",
    UPLOAD_DIR=str(_test_root / "uploads"),
    REDIS_URL=_root_redis.url,
    ES_HOST="http://127.0.0.1:1",
    OLLAMA_HOST="http://127.0.0.1:1",
    HF_HUB_OFFLINE="1",
    TRANSFORMERS_OFFLINE="1",
    HF_HOME=str(_test_root / "huggingface"),
    TORCH_HOME=str(_test_root / "torch"),
    XDG_CACHE_HOME=str(_test_root / "cache"),
    HTTP_PROXY="http://127.0.0.1:1",
    HTTPS_PROXY="http://127.0.0.1:1",
    ALL_PROXY="http://127.0.0.1:1",
    NO_PROXY="127.0.0.1,localhost",
    IDENTITY_SERVICE_URL="http://127.0.0.1:1",
    INGESTION_SERVICE_URL="http://127.0.0.1:1",
    RAG_SERVICE_URL="http://127.0.0.1:1",
    GEMINI_API_KEY="",
    JWT_SECRET="isolated-test-signing-secret-not-for-deployment",
    JWT_ALGORITHM="HS256",
    ADMIN_INITIAL_PASSWORD="isolated-admin-password",
)


def pytest_unconfigure(config):
    if _root_redis is not None:
        _root_redis.cleanup()
    _test_resources.cleanup()


__all__ = ["start_redis_server", "RedisServer", "find_redis_binary"]
