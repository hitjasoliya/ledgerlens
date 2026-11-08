"""Real, owned Redis with persistent data and explicit outage/crash controls."""
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import redis


def find_redis_binary() -> Path:
    override = os.environ.get("REDIS_SERVER_BIN")
    if override:
        candidate = Path(override).expanduser().resolve()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        raise RuntimeError("REDIS_SERVER_BIN must name an executable redis-server")
    installed = shutil.which("redis-server")
    if installed:
        return Path(installed).resolve()
    local = (
        Path(__file__).resolve().parents[3]
        / ".scratch/ledgerlens-hardening/runtime/redis-7.4.11/src/redis-server"
    )
    if local.is_file() and os.access(local, os.X_OK):
        return local
    raise RuntimeError(
        "Install Redis 7 on PATH or set REDIS_SERVER_BIN. "
        "Authorization tests require a real, disposable Redis server."
    )


class RedisServer:
    def __init__(self, data_dir=None, prefix="ledgerlens-redis-"):
        self.binary = find_redis_binary()
        self._temporary = tempfile.TemporaryDirectory(prefix=prefix) if data_dir is None else None
        self.data_dir = Path(self._temporary.name if self._temporary else data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        self.process = None
        self._log = None

    @property
    def url(self):
        return f"redis://127.0.0.1:{self.port}/0"

    def get_client(self):
        return redis.Redis.from_url(
            self.url, decode_responses=True,
            socket_timeout=2, socket_connect_timeout=2,
        )

    def start(self):
        if self.process is not None and self.process.poll() is None:
            return self
        log_path = self.data_dir / "redis.log"
        self._log = log_path.open("a+")
        client = self.get_client()
        try:
            self.process = subprocess.Popen(
                [str(self.binary), "--bind", "127.0.0.1", "--port", str(self.port),
                 "--dir", str(self.data_dir), "--appendonly", "yes",
                 "--appendfsync", "always", "--maxmemory-policy", "noeviction",
                 "--protected-mode", "yes", "--save", ""],
                cwd=self.data_dir, stdout=self._log, stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(f"Owned Redis exited: {log_path.read_text()}")
                try:
                    reported_pid = client.info("server")["process_id"]
                except redis.RedisError:
                    time.sleep(0.05)
                    continue
                if reported_pid != self.process.pid:
                    raise RuntimeError("Redis port occupied by a different process")
                return self
            raise RuntimeError(f"Owned Redis startup timed out: {log_path.read_text()}")
        except BaseException:
            self.stop(crash=True)
            raise
        finally:
            client.connection_pool.disconnect()

    def stop(self, *, crash=False):
        process, self.process = self.process, None
        try:
            if process is not None:
                if process.poll() is None:
                    if crash:
                        process.kill()
                    else:
                        process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        finally:
            if self._log is not None:
                self._log.close()
                self._log = None

    def restart(self, *, crash=False):
        self.stop(crash=crash)
        return self.start()

    def cleanup(self):
        try:
            self.stop()
        finally:
            if self._temporary is not None:
                self._temporary.cleanup()
                self._temporary = None


def start_redis_server(data_dir=None, prefix="ledgerlens-redis-"):
    server = RedisServer(data_dir=data_dir, prefix=prefix)
    try:
        return server.start()
    except BaseException:
        server.cleanup()
        raise
