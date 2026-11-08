from __future__ import annotations
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

root_dir = Path(__file__).resolve().parent.parent.parent
common_path = str(root_dir / "packages" / "common" / "src")
if common_path not in sys.path:
    sys.path.insert(0, common_path)

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.datastructures import Headers
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from common.auth import get_current_user, get_redis_client
from common.config import settings
from common.http import configure_validation_errors
from common.schemas import HealthResponse

logger = logging.getLogger("gateway")

# Maximum upload body: 50 MiB file + 1 MiB bounded multipart overhead
MAX_UPLOAD_BODY_BYTES = settings.UPLOAD_MAX_BYTES + (1024 * 1024)

# Standard RFC 7230 / RFC 9110 hop-by-hop headers
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # App-owned HTTP client with explicit timeout and connection limits
    timeout = httpx.Timeout(settings.REQUEST_TIMEOUT_SECONDS, connect=10.0)
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=200)
    app.state.client = httpx.AsyncClient(timeout=timeout, limits=limits)
    try:
        yield
    finally:
        await app.state.client.aclose()



app = FastAPI(title="LedgerLens API Gateway", lifespan=lifespan)
configure_validation_errors(app)
protected = APIRouter(dependencies=[Depends(get_current_user)])

# Configure explicit CORS origins (default empty list enforces same-origin)
cors_origins = settings.CORS_ORIGINS or []

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_client(request: Request) -> httpx.AsyncClient:
    client = getattr(request.app.state, "client", None)
    if client is None or client.is_closed:
        raise RuntimeError(
            "Gateway HTTP client is uninitialized; requests must execute within application lifespan"
        )
    return client


def _filter_client_headers(headers: Headers) -> dict[str, str]:
    """Strip RFC hop-by-hop headers, named Connection tokens, and caller identity overrides."""
    # Parse Connection header for token-named headers to strip
    connection_val = headers.get("connection", "")
    connection_tokens = {
        token.strip().lower() for token in connection_val.split(",") if token.strip()
    }

    filtered = {}
    for name, value in headers.items():
        lower = name.lower()
        if lower in HOP_BY_HOP_HEADERS or lower in connection_tokens:
            continue
        # Strip all caller-supplied identity override headers
        if (
            lower.startswith("x-user")
            or lower.startswith("x-role")
            or lower.startswith("x-principal")
            or lower.startswith("x-auth-")
            or lower.startswith("x-account")
            or lower.startswith("x-identity")
        ):
            continue
        filtered[name] = value
    return filtered


def _filter_downstream_response_headers(headers: httpx.Headers) -> dict[str, str]:
    """Strip RFC hop-by-hop headers and named Connection tokens from downstream responses."""
    connection_val = headers.get("connection", "")
    connection_tokens = {
        token.strip().lower() for token in connection_val.split(",") if token.strip()
    }

    response_headers = {}
    for k, v in headers.items():
        lower = k.lower()
        if (
            lower in HOP_BY_HOP_HEADERS
            or lower in connection_tokens
            or lower == "content-encoding"
        ):
            continue
        response_headers[k] = v
    return response_headers


async def bounded_body_stream(request: Request, max_bytes: int) -> AsyncGenerator[bytes, None]:
    """Stream request body while enforcing bounded upload limits."""
    bytes_received = 0
    async for chunk in request.stream():
        bytes_received += len(chunk)
        if bytes_received > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Upload stream exceeds maximum allowed size of {max_bytes} bytes",
            )
        yield chunk


async def safe_response_streamer(resp: httpx.Response) -> AsyncGenerator[bytes, None]:
    """Stream downstream bytes with guaranteed connection cleanup on completion or cancellation."""
    try:
        async for chunk in resp.aiter_bytes():
            yield chunk
    finally:
        await resp.aclose()


async def forward_request(target_url: str, request: Request) -> Response:
    client = get_client(request)
    headers = _filter_client_headers(request.headers)

    # Fast check on declared Content-Length header
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_UPLOAD_BODY_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Request body exceeds maximum allowed size of {MAX_UPLOAD_BODY_BYTES} bytes",
                )
        except ValueError:
            pass

    # Stream body for mutating methods; GET/HEAD/OPTIONS have no body
    if request.method in ("GET", "HEAD", "OPTIONS"):
        req_content = None
    elif request.method == "DELETE" and not content_length:
        req_content = None
    else:
        req_content = bounded_body_stream(request, MAX_UPLOAD_BODY_BYTES)

    params = list(request.query_params.multi_items()) if request.query_params else None

    req = client.build_request(
        method=request.method,
        url=target_url,
        headers=headers,
        params=params,
        content=req_content,
    )

    try:
        resp = await client.send(req, stream=True)
    except HTTPException:
        raise
    except httpx.RequestError as exc:
        # Unwrap transport exception chain to uncover bounded_body_stream HTTPException (e.g. 413)
        current: Optional[BaseException] = exc
        cause_http_exc: Optional[HTTPException] = None
        while current is not None:
            if isinstance(current, HTTPException):
                cause_http_exc = current
                break
            current = current.__cause__ or getattr(current, "__context__", None)
        if cause_http_exc is not None:
            raise cause_http_exc

        logger.error("Error forwarding request to downstream service: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Downstream service unavailable",
        )

    response_headers = _filter_downstream_response_headers(resp.headers)

    return StreamingResponse(
        safe_response_streamer(resp),
        status_code=resp.status_code,
        headers=response_headers,
        media_type=resp.headers.get("content-type"),
    )


# Public Endpoints
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@app.get("/ready")
async def ready(request: Request):
    client = get_client(request)
    status_details = {}
    is_ready = True

    # Check downstream microservices readiness strictly (NEVER fall back to /health)
    services = [
        ("identity", settings.IDENTITY_SERVICE_URL),
        ("ingestion", settings.INGESTION_SERVICE_URL),
        ("rag", settings.RAG_SERVICE_URL),
    ]
    for name, url in services:
        try:
            resp = await client.get(f"{url}/ready", timeout=3.0)
            if resp.status_code == 200:
                status_details[name] = "ready"
            else:
                status_details[name] = f"degraded ({resp.status_code})"
                is_ready = False
        except Exception as exc:
            logger.warning("Downstream readiness check failed for %s: %s", name, type(exc).__name__)
            status_details[name] = "unavailable"
            is_ready = False

    # Check Redis revocation store readiness
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        status_details["redis"] = "connected"
    except Exception as exc:
        logger.warning("Gateway Redis readiness probe failed: %s", type(exc).__name__)
        status_details["redis"] = "unavailable"
        is_ready = False

    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "degraded", "dependencies": status_details},
        )
    return {"status": "ready", "dependencies": status_details}


@app.post("/api/auth/login")
async def login_proxy(request: Request):
    return await forward_request(
        f"{settings.IDENTITY_SERVICE_URL}/api/auth/login", request
    )


# Protected Endpoints (Token verified before forwarding)
@protected.api_route("/api/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def identity_auth_proxy(path: str, request: Request):
    target = f"{settings.IDENTITY_SERVICE_URL}/api/auth/{path}"
    return await forward_request(target, request)


@protected.api_route("/api/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@protected.api_route("/api/users", methods=["GET", "POST"])
async def identity_users_proxy(request: Request, path: str = ""):
    target = (
        f"{settings.IDENTITY_SERVICE_URL}/api/users/{path}"
        if path
        else f"{settings.IDENTITY_SERVICE_URL}/api/users"
    )
    return await forward_request(target, request)


@protected.api_route("/api/documents/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@protected.api_route("/api/documents", methods=["GET", "POST", "DELETE"])
async def documents_proxy(request: Request, path: str = ""):
    target = f"{settings.INGESTION_SERVICE_URL}/api/documents" + (f"/{path}" if path else "")
    return await forward_request(target, request)


@protected.api_route("/api/jobs/{path:path}", methods=["GET"])
async def jobs_proxy(request: Request, path: str):
    return await forward_request(f"{settings.INGESTION_SERVICE_URL}/api/jobs/{path}", request)


@protected.api_route("/api/chat/{path:path}", methods=["GET", "POST", "DELETE"])
async def rag_chat_proxy(request: Request, path: str):
    return await forward_request(f"{settings.RAG_SERVICE_URL}/api/chat/{path}", request)


app.include_router(protected)
