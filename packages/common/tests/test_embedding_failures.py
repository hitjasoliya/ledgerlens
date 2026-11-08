"""Provider corruption must never become apparently valid financial evidence."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest

from common.config import settings
from common.search import DependencyUnavailable, Embedder


@pytest.fixture
def provider(monkeypatch):
    state = {"status": 200, "body": {"embeddings": [[1.0, 0.0, 0.0]]}}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.dumps(state["body"]).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "OLLAMA_HOST", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(settings, "EMBEDDING_DIMS", 3)
    client = Embedder()
    try:
        yield state, client
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("embeddings", [
    [[1.0, 2.0]],
    [[0.0, 0.0, 0.0]],
    [[float("nan"), 0.0, 1.0]],
    [[True, 0.0, 1.0]],
    [["1", 0.0, 1.0]],
    [],
])
def test_incompatible_embeddings_are_explicit_failures(provider, embeddings):
    state, client = provider
    state["body"] = {"embeddings": embeddings}
    with pytest.raises(DependencyUnavailable):
        client.embed_query("FY2025 revenue")


def test_provider_outage_is_not_substituted_with_semantic_evidence(provider):
    state, client = provider
    state["status"] = 503
    with pytest.raises(DependencyUnavailable, match="unavailable"):
        client.embed_query("FY2025 revenue")
