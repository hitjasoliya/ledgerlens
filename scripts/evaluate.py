#!/usr/bin/env python3
"""LedgerLens Financial Evaluation Suite.

Executes reproducible, isolated evaluation of the four real microservices:
1. Spawns disposable database, uploads, and Redis harness.
2. Creates a unique Elasticsearch index (e.g. ledgerlens_eval_{run_id}).
3. Launches the four real microservices (Identity, Ingestion, RAG, Gateway) on owned loopback ports.
4. Generates and ingests deterministic synthetic financial PDFs:
   - alpha_fy2024_audited_report.pdf (Audited financials, known correct numbers)
   - alpha_fy2024_draft_projections.pdf (Preliminary draft with CONFLICTING figures on Page 1)
5. Tests key behavioral cases:
   - Grounded financial query (known number answer, correct document/page, conflict excluded)
   - Table units and period header extraction
   - Truthful abstention on missing evidence
   - Unauthorized-access denial across chat sessions, document downloads, and anonymous calls
6. Supports three explicit execution modes:
   - Live Model Evaluation (--live): Calls live Gemini API using GEMINI_API_KEY from environment
     (never passed via CLI argv to prevent secret exposure in process tables); honestly reports
     provider errors (e.g. invalid API key) without disguising failures or using fake fallbacks.
   - Deterministic Adapter (--deterministic): Uses test-only deterministic adapter for local
     behavioral testing of gateway, search, and citation plumbing (explicitly labeled NOT live quality).
   - Default Mode: Incurs zero charges; honestly records provider unavailability while evaluating
     abstention, authorization, and direct search isolation.
7. Measures actual end-to-end latency and outcomes.
8. Produces an evidence-backed JSON report with configuration context, limitations,
   and verified claim checklist where EVERY claim is derived from actual outcomes.
9. Tears down ONLY its owned resources, preserving all external data.
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import signal
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure repository root and common package are on sys.path
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
_common_path = _project_root / "packages" / "common" / "src"

if str(_common_path) not in sys.path:
    sys.path.insert(0, str(_common_path))
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import httpx
from elasticsearch import Elasticsearch

from evaluation.fixtures import (
    AUDITED_REPORT_FILENAME,
    DRAFT_PROJECTIONS_FILENAME,
    compute_file_sha256,
    generate_evaluation_pdfs,
    get_evaluation_cases,
)
from services.gateway.tests.redis_harness import start_redis_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("evaluate")


def mask_secrets(text: str, secret_patterns: Optional[List[str]] = None) -> str:
    """Masks authorization tokens, API keys, and secret values in text and logs."""
    if not text:
        return text
    # Mask Bearer tokens
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer [REDACTED]", text, flags=re.IGNORECASE)
    # Mask common Google GenAI / Gemini API key pattern (AIza...)
    sanitized = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_API_KEY]", sanitized)
    # Mask explicit known secret strings passed in
    if secret_patterns:
        for secret in secret_patterns:
            if secret and len(secret) >= 6:
                sanitized = sanitized.replace(secret, "[REDACTED]")
    return sanitized


class EvaluationRunner:
    def __init__(
        self,
        es_host: str,
        ollama_host: str,
        embedding_model: str = "embeddinggemma",
        embedding_dims: int = 768,
        gemini_model: str = "gemini-3.5-flash-lite",
        live_generation: bool = False,
        deterministic_adapter: bool = False,
        fixtures_dir: Optional[Path] = None,
        timeout: float = 120.0,
        keep_resources: bool = False,
    ):
        self.es_host = es_host.rstrip("/")
        self.ollama_host = ollama_host.rstrip("/")
        self.embedding_model = embedding_model
        self.embedding_dims = embedding_dims
        self.gemini_model = gemini_model
        # Read API key strictly from environment to avoid process argv exposure
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.live_generation = live_generation
        self.deterministic_adapter = deterministic_adapter
        self.fixtures_dir = (fixtures_dir or (_project_root / "evaluation")).resolve()
        self.timeout = timeout
        self.keep_resources = keep_resources

        # Determine explicit mode label
        if self.live_generation:
            self.mode_label = "live"
        elif self.deterministic_adapter:
            self.mode_label = "deterministic_adapter"
        else:
            self.mode_label = "default_dry_run"

        self.run_id = uuid.uuid4().hex[:10]
        self.unique_es_index = f"ledgerlens_eval_{self.run_id}"
        self.admin_password = f"eval-admin-pass-{self.run_id}-X9#"
        self.jwt_secret = f"eval-jwt-secret-token-key-32-chars-long-{self.run_id}!"

        self.temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self.resources_path: Optional[Path] = None
        self.redis_server = None
        self.listeners: Dict[str, socket.socket] = {}
        self.urls: Dict[str, str] = {}
        self.processes: List[subprocess.Popen] = []
        self.log_files: List[Any] = []
        self.pdf_files: Dict[str, Path] = {}
        self.documents_metadata: Dict[str, Any] = {}
        self.readiness_details: Dict[str, Any] = {}
        self.gateway_ready = False

    def setup_disposable_resources(self) -> None:
        """Sets up disposable SQLite, uploads, Redis server, and loopback listeners."""
        logger.info("Initializing disposable evaluation harness (run_id=%s, mode=%s)", self.run_id, self.mode_label)
        self.temp_dir = tempfile.TemporaryDirectory(prefix=f"ledgerlens-eval-{self.run_id}-")
        self.resources_path = Path(self.temp_dir.name).resolve()
        uploads_dir = self.resources_path / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = self.resources_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # 1. Start owned Redis server
        logger.info("Starting isolated Redis server...")
        self.redis_server = start_redis_server(
            data_dir=self.resources_path / "redis",
            prefix=f"ledgerlens-eval-redis-{self.run_id}-",
        )

        # 2. Allocate 4 owned loopback ports for the microservices
        for name in ("identity", "ingestion", "rag", "gateway"):
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            self.listeners[name] = listener
            self.urls[name] = f"http://127.0.0.1:{listener.getsockname()[1]}"

        logger.info(
            "Bound loopback services: Gateway=%s, Identity=%s, Ingestion=%s, RAG=%s",
            self.urls["gateway"],
            self.urls["identity"],
            self.urls["ingestion"],
            self.urls["rag"],
        )

        # 3. Ensure synthetic PDF fixtures exist
        self.fixtures_dir.mkdir(parents=True, exist_ok=True)
        audited_pdf = self.fixtures_dir / AUDITED_REPORT_FILENAME
        draft_pdf = self.fixtures_dir / DRAFT_PROJECTIONS_FILENAME

        if not audited_pdf.exists() or not draft_pdf.exists():
            logger.info("Generating synthetic financial PDF fixtures in %s...", self.fixtures_dir)
            self.pdf_files = generate_evaluation_pdfs(self.fixtures_dir)
        else:
            self.pdf_files = {
                "audited": audited_pdf,
                "draft": draft_pdf,
            }

    def start_services(self) -> None:
        """Launches the 4 real microservices on loopback with isolated environment."""
        assert self.resources_path is not None
        assert self.redis_server is not None

        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(_project_root), str(_common_path))),
            "ENV": "test",
            "DATABASE_URL": f"sqlite:///{self.resources_path / 'eval.sqlite'}",
            "UPLOAD_DIR": str(self.resources_path / "uploads"),
            "REDIS_URL": self.redis_server.url,
            "ES_HOST": self.es_host,
            "ES_INDEX": self.unique_es_index,
            "OLLAMA_HOST": self.ollama_host,
            "EMBEDDING_MODEL": self.embedding_model,
            "EMBEDDING_DIMS": str(self.embedding_dims),
            "GEMINI_MODEL": self.gemini_model,
            "GEMINI_API_KEY": self.gemini_api_key if self.live_generation else "",
            "IDENTITY_SERVICE_URL": self.urls["identity"],
            "INGESTION_SERVICE_URL": self.urls["ingestion"],
            "RAG_SERVICE_URL": self.urls["rag"],
            "JWT_SECRET": self.jwt_secret,
            "JWT_ALGORITHM": "HS256",
            "ADMIN_INITIAL_PASSWORD": self.admin_password,
            "INGESTION_WORKERS": "2",
            "JOB_LEASE_SECONDS": "60",
            "WORKER_POLL_SECONDS": "0.5",
            "AI_TIMEOUT_SECONDS": str(self.timeout),
            # Default CPU device for Docling to prevent auto-MPS errors on macOS
            "DOCLING_DEVICE": "cpu",
            # Explicitly set adapter mode: NEVER accidentally inherit from ambient environment
            "RAG_GENERATOR_ADAPTER": "deterministic" if self.deterministic_adapter else "gemini",
        }

        if self.deterministic_adapter:
            logger.info("Explicitly configured RAG_GENERATOR_ADAPTER=deterministic for local behavioral testing")
        else:
            logger.info("RAG_GENERATOR_ADAPTER explicitly disabled (production/live generator shape)")

        with httpx.Client(timeout=10.0, trust_env=False) as http:
            # Start identity -> ingestion -> rag -> gateway in strict sequence
            for name in ("identity", "ingestion", "rag", "gateway"):
                listener = self.listeners[name]
                log_path = self.resources_path / "logs" / f"{name}.log"
                log_file = log_path.open("w+")
                self.log_files.append(log_file)

                logger.info("Starting %s service on %s...", name, self.urls[name])
                proc = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        f"services.{name}.main:app",
                        "--fd",
                        str(listener.fileno()),
                        "--log-level",
                        "warning",
                    ],
                    cwd=self.resources_path,
                    env=env,
                    pass_fds=(listener.fileno(),),
                    start_new_session=True,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                )
                self.processes.append(proc)

                # Poll health until ready
                deadline = time.monotonic() + 45.0
                healthy = False
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        break
                    try:
                        res = http.get(f"{self.urls[name]}/health", timeout=1.0)
                        if res.status_code == 200:
                            healthy = True
                            break
                    except httpx.TransportError:
                        time.sleep(0.1)

                if not healthy or proc.poll() is not None:
                    log_file.seek(0)
                    error_log = mask_secrets(
                        log_file.read(),
                        [self.admin_password, self.jwt_secret, self.gemini_api_key],
                    )
                    raise RuntimeError(f"Service '{name}' failed to start:\n{error_log}")

                listener.close()

            # Probe gateway readiness probe truthfully; do NOT substitute degraded with health
            try:
                res = http.get(f"{self.urls['gateway']}/ready", timeout=3.0)
                if res.status_code == 200:
                    self.gateway_ready = True
                    self.readiness_details = res.json()
                    logger.info("Gateway /ready confirmed full readiness (status=200)")
                else:
                    self.gateway_ready = False
                    self.readiness_details = res.json() if res.headers.get("content-type", "").startswith("application/json") else {"detail": res.text}
                    logger.info("Gateway /ready reported degraded (status=%d): %s", res.status_code, self.readiness_details)
            except Exception as exc:
                self.gateway_ready = False
                self.readiness_details = {"error": str(exc)}
                logger.info("Gateway /ready check encountered exception: %s", exc)

    def create_synthetic_accounts(self) -> Dict[str, Dict[str, Any]]:
        """Bootstraps admin and creates synthetic analyst and unauthorized employees."""
        gateway = self.urls["gateway"]
        with httpx.Client(timeout=10.0, trust_env=False) as http:
            # Login as initial admin
            res = http.post(
                f"{gateway}/api/auth/login",
                json={"username": "admin", "password": self.admin_password},
            )
            res.raise_for_status()
            admin_data = res.json()
            admin_token = admin_data["access_token"]
            admin_headers = {"Authorization": f"Bearer {admin_token}"}

            users = {
                "admin": {
                    "token": admin_token,
                    "headers": admin_headers,
                    "user": admin_data.get("user", {}),
                }
            }

            # Create analyst and unauthorized employees
            for role_name in ("analyst", "unauthorized"):
                username = f"eval_{role_name}_{self.run_id}"
                password = f"pass_{self.run_id}_Aa1!"
                res = http.post(
                    f"{gateway}/api/users",
                    headers=admin_headers,
                    json={"username": username, "password": password, "role": "employee"},
                )
                res.raise_for_status()

                # Login as the new employee
                res_login = http.post(
                    f"{gateway}/api/auth/login",
                    json={"username": username, "password": password},
                )
                res_login.raise_for_status()
                login_data = res_login.json()
                token = login_data["access_token"]
                users[role_name] = {
                    "username": username,
                    "token": token,
                    "headers": {"Authorization": f"Bearer {token}"},
                    "user": login_data.get("user", {}),
                }

            logger.info("Bootstrapped accounts: admin, %s, %s", users["analyst"]["username"], users["unauthorized"]["username"])
            return users

    def ingest_synthetic_pdfs(self, analyst_headers: Dict[str, str]) -> Dict[str, str]:
        """Ingests the two synthetic PDFs via Gateway and polls until searchable."""
        gateway = self.urls["gateway"]
        document_ids = {}

        with httpx.Client(timeout=self.timeout, trust_env=False) as http:
            for key, filename in (
                ("audited", AUDITED_REPORT_FILENAME),
                ("draft", DRAFT_PROJECTIONS_FILENAME),
            ):
                pdf_path = self.pdf_files[key]
                logger.info("Uploading %s (%s)...", filename, key)
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()

                t0 = time.perf_counter()
                res = http.post(
                    f"{gateway}/api/documents",
                    headers=analyst_headers,
                    files={"file": (filename, pdf_bytes, "application/pdf")},
                )
                res.raise_for_status()
                ingest_data = res.json()
                doc_id = ingest_data["id"]
                job_id = ingest_data["job_id"]
                document_ids[key] = doc_id

                # Poll job until completed
                deadline = time.monotonic() + self.timeout
                completed = False
                while time.monotonic() < deadline:
                    job_res = http.get(
                        f"{gateway}/api/jobs/{job_id}",
                        headers=analyst_headers,
                    )
                    if job_res.status_code == 200:
                        job_data = job_res.json()
                        job_status = job_data.get("status")
                        if job_status == "completed":
                            completed = True
                            elapsed = time.perf_counter() - t0
                            logger.info(
                                "Document %s indexed successfully in %.2fs (chunks: %d)",
                                filename,
                                elapsed,
                                job_data.get("chunks_indexed", 0),
                            )
                            break
                        if job_status == "failed":
                            err = job_data.get("error_message", "Unknown ingestion error")
                            raise RuntimeError(f"Ingestion failed for {filename}: {err}")
                    time.sleep(0.5)

                if not completed:
                    raise TimeoutError(f"Ingestion timed out for {filename} after {self.timeout}s")

                self.documents_metadata[key] = {
                    "document_id": doc_id,
                    "filename": filename,
                    "sha256": compute_file_sha256(pdf_path),
                }

        return document_ids

    def verify_elasticsearch_retrieval(
        self,
        doc_audited_id: str,
        doc_draft_id: str,
    ) -> Dict[str, Any]:
        """Exercise production embedding and RRF search, not a copied query."""
        environment = {
            **os.environ,
            "ENV": "test",
            "JWT_SECRET": self.jwt_secret,
            "ADMIN_INITIAL_PASSWORD": self.admin_password,
            "GEMINI_API_KEY": "",
            "ES_HOST": self.es_host,
            "ES_INDEX": self.unique_es_index,
            "ES_USERNAME": "",
            "ES_PASSWORD": "",
            "OLLAMA_HOST": self.ollama_host,
            "EMBEDDING_MODEL": self.embedding_model,
            "EMBEDDING_DIMS": str(self.embedding_dims),
            "PYTHONPATH": os.pathsep.join((str(_project_root), str(_common_path))),
        }
        # The subprocess gives the real clients isolated configuration without
        # mutating the parent's settings or replacing either search path.
        result = subprocess.run(
            [sys.executable, "-c", """
import json
import sys
from common.search import Embedder, ESClient
embedder, search = Embedder(), ESClient()
try:
    question = "What was Alpha Technologies' audited total revenue for fiscal year 2024?"
    hits = search.hybrid_search(question, embedder.embed_query(question), {sys.stdin.read(): 1})
    fields = ("document_id", "page_number", "item_type", "text", "version")
    print(json.dumps([{key: hit[key] for key in fields} for hit in hits]))
finally:
    embedder.close()
    search.close()
"""],
            input=doc_audited_id, text=True, capture_output=True, check=True,
            env=environment, timeout=self.timeout,
        )
        hits = json.loads(result.stdout)
        top_hit = hits[0] if hits else {}
        contains_audited_figure = any("$1,250.0" in hit["text"] for hit in hits)
        contains_draft_figure = any("$1,100.0" in hit["text"] for hit in hits)
        leaked_draft_doc = any(hit["document_id"] == doc_draft_id for hit in hits)
        return {
            "status": "passed" if contains_audited_figure and not leaked_draft_doc and not contains_draft_figure else "failed",
            "top_chunk_document_id": top_hit.get("document_id"),
            "top_chunk_page": top_hit.get("page_number"),
            "top_chunk_item_type": top_hit.get("item_type"),
            "contains_expected_audited_figure": contains_audited_figure,
            "contains_conflicting_draft_figure": contains_draft_figure,
            "leaked_conflicting_draft_doc": leaked_draft_doc,
            "total_chunks_returned": len(hits),
        }

    def run_case(
        self,
        case: Dict[str, Any],
        users: Dict[str, Dict[str, Any]],
        document_ids: Dict[str, str],
        http: httpx.Client,
    ) -> Dict[str, Any]:
        """Executes a single evaluation case with unified HTTP dispatch and scoring."""
        gateway = self.urls["gateway"]
        case_id = case["case_id"]
        category = case["category"]
        t0 = time.perf_counter()

        logger.info("Executing case %s: %s (%s)...", case_id, case["name"], category)

        # -------------------------------------------------------------
        # CATEGORY 1: Grounded Financial Queries (FIN-EVAL-01, FIN-EVAL-02)
        # -------------------------------------------------------------
        if category == "grounded_financial_query":
            # 1. Create chat session selecting ONLY the audited document
            res_sess = http.post(
                f"{gateway}/api/chat/sessions",
                headers=users["analyst"]["headers"],
                json={"title": f"Eval Session {case_id}", "selected_document_ids": [document_ids["audited"]]},
            )
            res_sess.raise_for_status()
            session_id = res_sess.json()["id"]

            # 2. Dispatch question through Gateway to RAG
            res_chat = http.post(
                f"{gateway}/api/chat/sessions/{session_id}/messages",
                headers=users["analyst"]["headers"],
                json={ "message": case["question"]},
            )
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

            base_result = {
                "case_id": case_id,
                "name": case["name"],
                "category": category,
                "question": case["question"],
                "selected_documents": [AUDITED_REPORT_FILENAME],
                "excluded_documents": [DRAFT_PROJECTIONS_FILENAME],
                "expected_figure": case["expected_figure"],
                "conflicting_figure_to_reject": case["conflicting_figure_to_reject"],
                "expected_page": case["target_page"],
                "status_code": res_chat.status_code,
                "latency_ms": elapsed_ms,
                "execution_mode": self.mode_label,
            }

            if res_chat.status_code == 200:
                chat_data = res_chat.json()
                answer = chat_data.get("answer", "")
                citations = chat_data.get("citations", [])

                contains_expected = any(tok in answer for tok in case["expected_figure_tokens"])
                contains_rejected = any(tok in answer for tok in case["conflicting_figure_tokens"])
                contains_units = all(
                    re.search(pattern, answer, re.IGNORECASE)
                    for pattern in case["expected_unit_patterns"]
                )
                cited_audited_page1 = any(
                    c.get("document_id") == document_ids["audited"] and c.get("page") == case["target_page"]
                    for c in citations
                )
                cited_conflicting_draft = any(c.get("document_id") == document_ids["draft"] for c in citations)

                passed = (
                    contains_expected
                    and not contains_rejected
                    and cited_audited_page1
                    and not cited_conflicting_draft
                    and contains_units
                )

                result = {
                    **base_result,
                    "outcome": "passed" if passed else "failed",
                    "actual_answer": answer,
                    "actual_citations": citations,
                    "chunks_used": chat_data.get("chunks_used", 0),
                    "checks": {
                        "contains_expected_figure": contains_expected,
                        "rejects_conflicting_draft_figure": not contains_rejected,
                        "cites_audited_page_1": cited_audited_page1,
                        "excludes_conflicting_draft_doc": not cited_conflicting_draft,
                        "contains_expected_currency_and_scale": contains_units,
                    },
                }
                if self.mode_label == "deterministic_adapter":
                    result["behavioral_adapter_warning"] = (
                        "DETERMINISTIC TEST ADAPTER: Verifies retrieval, grounding, and citation plumbing. "
                        "Does NOT represent live model generation quality or factual synthesis."
                    )
                return result

            # Non-200 responses
            error_body = mask_secrets(res_chat.text[:300], [self.admin_password, self.jwt_secret, self.gemini_api_key])
            if self.mode_label == "live" and res_chat.status_code == 503:
                # Honest provider failure reporting; no fake passes
                return {
                    **base_result,
                    "outcome": "provider_failure",
                    "provider_error": True,
                    "reason": f"Live evaluation request returned HTTP {res_chat.status_code}: {error_body}",
                    "notes": "Dependency failure recorded without fallback; inspect provider availability and configuration.",
                }
            elif self.mode_label == "default_dry_run" and res_chat.status_code == 503:
                # Honest provider unavailability reporting
                return {
                    **base_result,
                    "outcome": "provider_unavailable",
                    "reason": (
                        "Live Gemini generation omitted by default to prevent charges. "
                        "Pass --live with valid GEMINI_API_KEY, or --deterministic for local adapter."
                    ),
                }
            else:
                return {
                    **base_result,
                    "outcome": "failed",
                    "reason": f"Evaluation request returned unexpected HTTP {res_chat.status_code}: {error_body}",
                }

        # -------------------------------------------------------------
        # CATEGORY 2: Abstention on Missing Evidence (FIN-EVAL-03)
        # -------------------------------------------------------------
        elif category == "abstention":
            res_sess = http.post(
                f"{gateway}/api/chat/sessions",
                headers=users["analyst"]["headers"],
                json={"title": f"Eval Session {case_id}", "selected_document_ids": [document_ids["audited"]]},
            )
            res_sess.raise_for_status()
            session_id = res_sess.json()["id"]

            res_chat = http.post(
                f"{gateway}/api/chat/sessions/{session_id}/messages",
                headers=users["analyst"]["headers"],
                json={ "message": case["question"]},
            )
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

            if res_chat.status_code != 200:
                return {
                    "case_id": case_id,
                    "name": case["name"],
                    "category": category,
                    "question": case["question"],
                    "status_code": res_chat.status_code,
                    "outcome": "failed",
                    "latency_ms": elapsed_ms,
                    "reason": f"Expected HTTP 200 for abstention, got {res_chat.status_code}: {res_chat.text[:200]}",
                }

            chat_data = res_chat.json()
            answer = chat_data.get("answer", "").lower()
            citations = chat_data.get("citations", [])
            chunks_used = chat_data.get("chunks_used", 0)

            is_abstention = (
                "could not find sufficient information" in answer
                or "cannot answer" in answer
                or "not enough information" in answer
            )
            has_no_citations = len(citations) == 0
            has_zero_chunks = chunks_used == 0
            passed = is_abstention and has_no_citations and has_zero_chunks

            return {
                "case_id": case_id,
                "name": case["name"],
                "category": category,
                "question": case["question"],
                "status_code": res_chat.status_code,
                "outcome": "passed" if passed else "failed",
                "latency_ms": elapsed_ms,
                "actual_answer": chat_data.get("answer", ""),
                "chunks_used": chunks_used,
                "citations_count": len(citations),
                "checks": {
                    "contains_abstention_text": is_abstention,
                    "zero_chunks_used": has_zero_chunks,
                    "zero_citations": has_no_citations,
                },
            }

        # -------------------------------------------------------------
        # CATEGORY 3: Authorization Denial (FIN-EVAL-04, 05, 06)
        # -------------------------------------------------------------
        elif category == "authorization_denial":
            action = case["action"]

            if action == "create_chat_session_with_unshared_doc":
                # Unauthorized employee attempts to create session selecting another's doc
                res = http.post(
                    f"{gateway}/api/chat/sessions",
                    headers=users["unauthorized"]["headers"],
                    json={
                        "title": "Unauthorized Session",
                        "selected_document_ids": [document_ids["audited"]],
                    },
                )
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                # require_document returns 404 to avoid leaking document existence (privacy contract)
                passed = res.status_code == case["expected_status_code"]
                return {
                    "case_id": case_id,
                    "name": case["name"],
                    "category": category,
                    "actor": "unauthorized_employee",
                    "attempted_action": "POST /api/chat/sessions with unshared document",
                    "status_code": res.status_code,
                    "expected_status_code": case["expected_status_code"],
                    "outcome": "passed" if passed else "failed",
                    "latency_ms": elapsed_ms,
                    "response_detail": mask_secrets(res.text[:200]),
                }

            elif action == "get_document_source":
                res = http.get(
                    f"{gateway}/api/documents/{document_ids['audited']}/source",
                    headers=users["unauthorized"]["headers"],
                )
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                passed = res.status_code in (403, 404)
                return {
                    "case_id": case_id,
                    "name": case["name"],
                    "category": category,
                    "actor": "unauthorized_employee",
                    "attempted_action": "GET /api/documents/{id}/source",
                    "status_code": res.status_code,
                    "expected_status_code": case["expected_status_code"],
                    "outcome": "passed" if passed else "failed",
                    "latency_ms": elapsed_ms,
                    "response_detail": mask_secrets(res.text[:200]),
                }

            elif action == "access_protected_documents_endpoint":
                res = http.get(f"{gateway}/api/documents")
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                passed = res.status_code == 401
                return {
                    "case_id": case_id,
                    "name": case["name"],
                    "category": category,
                    "actor": "anonymous_caller",
                    "attempted_action": "GET /api/documents without credentials",
                    "status_code": res.status_code,
                    "expected_status_code": 401,
                    "outcome": "passed" if passed else "failed",
                    "latency_ms": elapsed_ms,
                    "response_detail": mask_secrets(res.text[:200]),
                }

        raise ValueError(f"Unknown evaluation case category: {category}")

    def teardown(self) -> None:
        """Tears down ONLY owned resources (processes, Redis, unique ES index, temp dir)."""
        logger.info("Tearing down evaluation resources for run_id=%s...", self.run_id)

        # 1. Terminate service processes
        for proc in reversed(self.processes):
            if proc.poll() is None:
                proc.terminate()
        for proc in reversed(self.processes):
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=2.0)

        for listener in self.listeners.values():
            try:
                listener.close()
            except Exception:
                pass

        for log in self.log_files:
            try:
                log.close()
            except Exception:
                pass

        # 2. Cleanup owned Redis instance
        if self.redis_server is not None:
            try:
                self.redis_server.cleanup()
            except Exception as exc:
                logger.warning("Error cleaning up owned Redis: %s", exc)

        # 3. Delete ONLY the unique Elasticsearch index for this run
        try:
            es = Elasticsearch(hosts=[self.es_host], request_timeout=10.0)
            if es.indices.exists(index=self.unique_es_index):
                es.indices.delete(index=self.unique_es_index)
                logger.info("Deleted unique evaluation ES index: %s", self.unique_es_index)
            es.close()
        except Exception as exc:
            logger.warning("Could not delete evaluation ES index %s: %s", self.unique_es_index, exc)

        # 4. Remove temp directory
        if self.temp_dir is not None and not self.keep_resources:
            try:
                self.temp_dir.cleanup()
                logger.info("Cleaned up temporary evaluation directory.")
            except Exception as exc:
                logger.warning("Could not delete temp directory: %s", exc)

    def run(self) -> Dict[str, Any]:
        """Main execution entry point."""
        report = {}
        try:
            self.setup_disposable_resources()
            self.start_services()

            users = self.create_synthetic_accounts()
            document_ids = self.ingest_synthetic_pdfs(users["analyst"]["headers"])

            # Direct Search Path Verification
            logger.info("Verifying Elasticsearch hybrid retrieval path...")
            retrieval_verification = self.verify_elasticsearch_retrieval(
                doc_audited_id=document_ids["audited"],
                doc_draft_id=document_ids["draft"],
            )

            # Execute evaluation cases
            cases = get_evaluation_cases()
            case_results = []
            with httpx.Client(timeout=self.timeout, trust_env=False) as http:
                for case in cases:
                    res = self.run_case(case, users, document_ids, http)
                    if case["case_id"] == "FIN-EVAL-01":
                        res["elasticsearch_retrieval_verification"] = retrieval_verification
                    case_results.append(res)

            # Calculate summary metrics
            latencies = [c["latency_ms"] for c in case_results if "latency_ms" in c]
            mean_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
            sorted_latencies = sorted(latencies)
            p95_idx = int(len(sorted_latencies) * 0.95)
            p95_latency = sorted_latencies[p95_idx] if sorted_latencies else 0.0

            passed_count = sum(1 for c in case_results if c.get("outcome") == "passed")
            failed_count = sum(1 for c in case_results if c.get("outcome") == "failed")
            provider_failure_count = sum(1 for c in case_results if c.get("outcome") == "provider_failure")
            provider_unavail_count = sum(1 for c in case_results if c.get("outcome") == "provider_unavailable")

            # Map case outcomes for claim derivation
            case_map = {c["case_id"]: c for c in case_results}
            case_1 = case_map.get("FIN-EVAL-01", {})
            case_2 = case_map.get("FIN-EVAL-02", {})
            case_3 = case_map.get("FIN-EVAL-03", {})
            case_4 = case_map.get("FIN-EVAL-04", {})
            case_5 = case_map.get("FIN-EVAL-05", {})
            case_6 = case_map.get("FIN-EVAL-06", {})

            # -------------------------------------------------------------------
            # DERIVE EVERY CLAIM STRICTLY FROM OBSERVED CASE OUTCOMES (NO HARDCODING)
            # -------------------------------------------------------------------
            # 1. Four Service Architecture Claim
            if len(self.processes) == 4 and all(p.poll() is None for p in self.processes):
                arch_claim_status = "demonstrated"
                arch_claim_evidence = f"Gateway ({self.urls['gateway']}) proxied to Identity, Ingestion, and RAG over dedicated loopback ports."
            else:
                arch_claim_status = "failed"
                arch_claim_evidence = "One or more required services exited unexpectedly during the evaluation run."

            # 2. Source Selection Isolation Claim
            search_passed = retrieval_verification.get("status") == "passed"
            chat_checks = case_1.get("checks", {})
            chat_isolated = (
                chat_checks.get("cites_audited_page_1")
                and chat_checks.get("excludes_conflicting_draft_doc")
                and chat_checks.get("rejects_conflicting_draft_figure")
            )
            if search_passed and chat_isolated:
                isolation_claim_status = "demonstrated"
                isolation_claim_evidence = (
                    "Production RRF search and returned chat citations excluded the conflicting unselected draft."
                )
            elif search_passed:
                isolation_claim_status = "demonstrated_in_search_only"
                isolation_claim_evidence = (
                    "Production RRF search excluded the conflicting draft; consult individual chat checks for their outcomes."
                )
            else:
                isolation_claim_status = "failed"
                isolation_claim_evidence = "Search or chat failed to isolate the selected document version from conflicting unselected documents."

            # 3. Abstention Claim
            if case_3.get("outcome") == "passed":
                abstention_claim_status = "demonstrated"
                abstention_claim_evidence = "Query for unmentioned solar capex yielded explicit abstention with zero chunks used and empty citations."
            else:
                abstention_claim_status = "failed"
                abstention_claim_evidence = f"Abstention case did not pass: {case_3.get('reason', 'Failed assertions')}"

            # 4. Authorization Denial Boundary Claim
            auth_passed = (
                case_4.get("outcome") == "passed"
                and case_5.get("outcome") == "passed"
                and case_6.get("outcome") == "passed"
            )
            if auth_passed:
                auth_claim_status = "demonstrated"
                auth_claim_evidence = (
                    "Unauthorized employee rejected with 404 for unshared chat session (privacy contract) "
                    "and 404 for source PDF; anonymous access rejected with 401."
                )
            else:
                failed_auth = [c["case_id"] for c in (case_4, case_5, case_6) if c.get("outcome") != "passed"]
                auth_claim_status = "failed"
                auth_claim_evidence = f"One or more authorization denial cases failed: {failed_auth}"

            # 5. Live Model Generation Claim
            if self.live_generation:
                if provider_failure_count > 0:
                    live_model_claim_status = "missing_prerequisite"
                    live_model_claim_evidence = (
                        "Live generation did not complete; inspect case-specific dependency failures. No model-quality result was obtained."
                    )
                elif case_1.get("outcome") == "passed" and case_2.get("outcome") == "passed":
                    live_model_claim_status = "demonstrated"
                    live_model_claim_evidence = "Live model generation produced grounded answers with valid citation tags."
                else:
                    live_model_claim_status = "failed"
                    live_model_claim_evidence = "Live model generated answer but failed verification checks."
            elif self.deterministic_adapter:
                live_model_claim_status = "not_exercised"
                live_model_claim_evidence = (
                    "Deterministic evaluation adapter used for behavioral plumbing tests; "
                    "live model generation quality was not exercised."
                )
            else:
                live_model_claim_status = "not_exercised"
                live_model_claim_evidence = "Live provider usage not requested by default to prevent charges."

            report = {
                "report_version": "1.0.0",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "run_id": self.run_id,
                "execution_mode": self.mode_label,
                "environment": {
                    "python_version": sys.version.split()[0],
                    "platform": platform.platform(),
                    "es_host": self.es_host,
                    "ollama_host": self.ollama_host,
                    "embedding_model": self.embedding_model,
                    "embedding_dims": self.embedding_dims,
                    "gemini_model": self.gemini_model,
                    "live_generation_requested": self.live_generation,
                    "deterministic_adapter_enabled": self.deterministic_adapter,
                    "unique_es_index": self.unique_es_index,
                    "gateway_readiness_status": "ready" if self.gateway_ready else "degraded",
                    "gateway_readiness_details": self.readiness_details,
                },
                "dataset": {
                    "name": "synthetic_deterministic_financial_evaluation",
                    "description": (
                        "Deterministic multi-page financial documents with conflicting values on Page 1, "
                        "explicit table units/period headers, and known correct figures."
                    ),
                    "documents": list(self.documents_metadata.values()),
                },
                "summary": {
                    "total_cases": len(case_results),
                    "passed": passed_count,
                    "failed": failed_count,
                    "provider_failure": provider_failure_count,
                    "provider_unavailable": provider_unavail_count,
                    "mean_latency_ms": mean_latency,
                    "p95_latency_ms": p95_latency,
                },
                "cases": case_results,
                "limitations_and_disclaimers": {
                    "universal_accuracy_disclaimer": (
                        "This evaluation is conducted on a small, synthetic deterministic fixture set "
                        "designed to verify specific security and correctness boundaries (source locking, "
                        "conflicting table isolation, abstention on missing evidence, and authorization denial). "
                        "Results from this small fixture set MUST NOT be interpreted as universal financial accuracy, "
                        "OCR universality, or enterprise production scale."
                    ),
                    "table_parsing_fidelity": (
                        "Table parsing relies on IBM Docling layout analysis and markdown export. Non-standard layouts, "
                        "complex nested headers, or poor quality scans may exhibit reduced extraction fidelity."
                    ),
                    "provider_variability": (
                        "Live LLM generation is subject to provider rate limits, latency fluctuations, and output non-determinism. "
                        "Deterministic provider adapters and offline retrieval gates do not substitute for live model quality measurements."
                    ),
                    "answer_scoring": (
                        "Financial cases use literal fixture-figure checks and explicit currency/scale patterns. "
                        "These are not semantic adjudication and may reject equivalent rescaled answers."
                    ),
                    "latency_measurement": (
                        "Per-case gateway HTTP latency includes session creation and the tested operation after "
                        "services/models and fixture indexing are warm. The aggregate mixes financial, abstention, "
                        "and denial cases; it excludes startup, model downloads, and ingestion and is not live-model latency."
                    ),
                    "authorization_boundary": (
                        "Authorization is SQL-authoritative across admin, owner, explicit recipient, and deny. "
                        "The four authorization cases represent distinct permission outcomes, not four isolated access-grant branches."
                    ),
                },
                "verified_claim_checklist": {
                    "four_service_architecture": {
                        "claim": "Deploys four distinct services (Identity, Ingestion, RAG, Gateway) on loopback ports.",
                        "status": arch_claim_status,
                        "evidence": arch_claim_evidence,
                    },
                    "source_selection_isolation": {
                        "claim": "Document-grounded retrieval strictly confines search to conversation-selected documents, excluding conflicting data.",
                        "status": isolation_claim_status,
                        "evidence": isolation_claim_evidence,
                    },
                    "abstention_on_insufficient_evidence": {
                        "claim": "The system abstains from generating speculative or hallucinated answers when evidence is absent.",
                        "status": abstention_claim_status,
                        "evidence": abstention_claim_evidence,
                    },
                    "authorization_denial_boundary": {
                        "claim": "Unshared document selection/source access and anonymous library access are denied.",
                        "status": auth_claim_status,
                        "evidence": auth_claim_evidence,
                    },
                    "live_model_generation": {
                        "claim": "Live Gemini answers match the fixture figures, units, and authorized document/page citations.",
                        "status": live_model_claim_status,
                        "evidence": live_model_claim_evidence,
                    },
                    "production_scale_and_universal_accuracy": {
                        "claim": "Guaranteed 100% financial accuracy across arbitrary corporate filings and production scale.",
                        "status": "not_demonstrated",
                        "evidence": "Evaluation tested a 2-document deterministic fixture set; universal accuracy is explicitly disclaimed.",
                    },
                },
            }

            return report

        finally:
            self.teardown()


def main():
    parser = argparse.ArgumentParser(
        description="Run LedgerLens Financial Evaluation Suite against disposable resources.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--es-host",
        default=os.environ.get("ES_HOST", "http://127.0.0.1:9200"),
        help="Elasticsearch host URL",
    )
    parser.add_argument(
        "--ollama-host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        help="Ollama host URL",
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("EMBEDDING_MODEL", "embeddinggemma"),
        help="Embedding model name",
    )
    parser.add_argument(
        "--embedding-dims",
        type=int,
        default=int(os.environ.get("EMBEDDING_DIMS", "768")),
        help="Embedding dimensions",
    )
    parser.add_argument(
        "--gemini-model",
        default=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        help="Gemini model name",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Enable live Gemini model calls using GEMINI_API_KEY from environment (honestly reports provider failures; default False avoids incurring charges)",
    )
    parser.add_argument(
        "--deterministic",
        action="store_true",
        default=False,
        help="Enable deterministic evaluation adapter for local behavioral testing without live provider calls (explicitly labeled as test infrastructure, not live model quality)",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=_project_root / "evaluation",
        help="Directory storing synthetic PDF fixtures",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to write JSON evaluation report",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Timeout in seconds for operations and ingestion",
    )
    parser.add_argument(
        "--keep-resources",
        action="store_true",
        default=False,
        help="Keep temporary SQLite and upload resources on exit (for debugging)",
    )

    args = parser.parse_args()

    runner = EvaluationRunner(
        es_host=args.es_host,
        ollama_host=args.ollama_host,
        embedding_model=args.embedding_model,
        embedding_dims=args.embedding_dims,
        gemini_model=args.gemini_model,
        live_generation=args.live,
        deterministic_adapter=args.deterministic,
        fixtures_dir=args.fixtures_dir,
        timeout=args.timeout,
        keep_resources=args.keep_resources,
    )

    print("=" * 70)
    print("LedgerLens Financial Evaluation Suite")
    print(f"Execution Mode:  {runner.mode_label.upper()}")
    print(f"ES Host:         {args.es_host}")
    print(f"Ollama Host:     {args.ollama_host}")
    print(f"Embedding Model: {args.embedding_model} ({args.embedding_dims} dims)")
    print(f"Live Gemini:     {'ENABLED' if args.live else 'DISABLED'}")
    print(f"Deterministic:   {'ENABLED' if args.deterministic else 'DISABLED'}")
    print("=" * 70)

    report = runner.run()

    # Output JSON report
    report_json = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report_json)
        print(f"\nEvaluation report written to: {args.output.resolve()}")
    else:
        print("\n" + report_json)

    # Print summary table
    summary = report.get("summary", {})
    print("\n" + "=" * 70)
    print("Evaluation Summary:")
    print(f"Mode:                 {runner.mode_label.upper()}")
    print(f"Total Cases:          {summary.get('total_cases', 0)}")
    print(f"Passed:               {summary.get('passed', 0)}")
    print(f"Failed:               {summary.get('failed', 0)}")
    print(f"Provider Failure:     {summary.get('provider_failure', 0)}")
    print(f"Provider Unavailable: {summary.get('provider_unavailable', 0)}")
    print(f"Mean Latency:         {summary.get('mean_latency_ms', 0.0)} ms")
    print(f"P95 Latency:          {summary.get('p95_latency_ms', 0.0)} ms")
    print("=" * 70)

    # Return exit code: 1 if any failure or provider_failure, else 0
    if summary.get("failed", 0) > 0 or summary.get("provider_failure", 0) > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
