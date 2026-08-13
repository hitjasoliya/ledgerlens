from __future__ import annotations
import logging
import sys
from pathlib import Path
import httpx

root_dir = Path(__file__).resolve().parent.parent.parent
common_path = str(root_dir / "packages" / "common" / "src")
if common_path not in sys.path:
    sys.path.insert(0, common_path)

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from common.config import settings
from common.auth import decode_access_token

logger = logging.getLogger(__name__)

app = FastAPI(title="LedgerLens API Gateway")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = httpx.AsyncClient(timeout=120.0)


@app.get("/health")
async def health():
    services_health = {}
    for name, url in [
        ("identity", settings.IDENTITY_SERVICE_URL),
        ("ingestion", settings.INGESTION_SERVICE_URL),
        ("rag", settings.RAG_SERVICE_URL),
    ]:
        try:
            r = await client.get(f"{url}/health", timeout=3.0)
            services_health[name] = r.json() if r.status_code == 200 else "unhealthy"
        except Exception:
            services_health[name] = "offline"

    return {"status": "ok", "services": services_health}


async def forward_request(
    target_url: str, request: Request, auth_required: bool = False
) -> Response:
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    authorization = headers.get("authorization")
    if authorization and authorization.startswith("Bearer "):
        try:
            token = authorization.split(" ")[1]
            payload = decode_access_token(token)
            headers["X-User-ID"] = payload.get("id") or payload.get("sub", "guest")
            headers["X-User-Name"] = payload.get("username") or payload.get("sub", "guest")
            headers["X-User-Role"] = payload.get("role", "employee")
        except Exception:
            if auth_required:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication token",
                )
    elif auth_required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required",
        )

    body = await request.body()
    try:
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=dict(request.query_params),
            content=body,
        )

        response_headers = {
            k: v
            for k, v in resp.headers.items()
            if k.lower() not in ("content-length", "transfer-encoding", "content-encoding")
        }

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=response_headers,
        )
    except Exception as exc:
        logger.error(f"Error forwarding request to {target_url}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unavailable: {exc}",
        )


# Identity Service Routes
@app.api_route("/api/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def identity_auth_proxy(path: str, request: Request):
    auth_required = path not in ["login"]
    target = f"{settings.IDENTITY_SERVICE_URL}/api/auth/{path}"
    return await forward_request(target, request, auth_required=auth_required)


@app.api_route("/api/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("/api/users", methods=["GET", "POST"])
async def identity_users_proxy(request: Request, path: str = ""):
    target = (
        f"{settings.IDENTITY_SERVICE_URL}/api/users/{path}"
        if path
        else f"{settings.IDENTITY_SERVICE_URL}/api/users"
    )
    return await forward_request(target, request, auth_required=True)


# Ingestion Service Routes
@app.api_route("/api/ingest/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("/api/ingest", methods=["POST"])
async def ingestion_proxy(request: Request, path: str = ""):
    target = (
        f"{settings.INGESTION_SERVICE_URL}/api/ingest/{path}"
        if path
        else f"{settings.INGESTION_SERVICE_URL}/api/ingest"
    )
    return await forward_request(target, request, auth_required=False)


@app.api_route("/api/documents/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("/api/documents", methods=["GET"])
async def documents_proxy(request: Request, path: str = ""):
    target = (
        f"{settings.INGESTION_SERVICE_URL}/api/documents/{path}"
        if path
        else f"{settings.INGESTION_SERVICE_URL}/api/documents"
    )
    return await forward_request(target, request, auth_required=False)


@app.api_route("/api/embeddings", methods=["DELETE"])
async def embeddings_proxy(request: Request):
    return await forward_request(
        f"{settings.INGESTION_SERVICE_URL}/api/embeddings",
        request,
        auth_required=False,
    )


# RAG Service Routes
@app.api_route("/api/chat/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("/api/chat", methods=["POST"])
async def rag_chat_proxy(request: Request, path: str = ""):
    target = (
        f"{settings.RAG_SERVICE_URL}/api/chat/{path}"
        if path
        else f"{settings.RAG_SERVICE_URL}/api/chat"
    )
    return await forward_request(target, request, auth_required=False)


@app.api_route("/api/session/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def rag_session_proxy(path: str, request: Request):
    target = f"{settings.RAG_SERVICE_URL}/api/session/{path}"
    return await forward_request(target, request, auth_required=False)
