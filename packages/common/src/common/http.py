"""Bound multipart input before Starlette can spool it to disk."""
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from common.config import settings
from common.schemas import PAGE_DEFAULT_LIMIT, PAGE_MAX_LIMIT


class _UploadBodyTooLarge(OSError):
    pass


class UploadBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/api/documents":
            await self.app(scope, receive, send)
            return
        # File bytes are independently bounded by ingestion. Multipart headers
        # and boundaries receive a fixed, bounded allowance at both HTTP hops.
        limit = settings.UPLOAD_MAX_BYTES + 1024 * 1024
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                length = int(declared)
                if length < 0:
                    raise ValueError
            except ValueError:
                await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(scope, receive, send)
                return
            if length > limit:
                await JSONResponse({"detail": "Upload body exceeds the allowed size"}, status_code=413)(scope, receive, send)
                return
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > limit:
                    raise _UploadBodyTooLarge
            return message

        try:
            await self.app(scope, bounded_receive, send)
        except _UploadBodyTooLarge:
            await JSONResponse({"detail": "Upload body exceeds the allowed size"}, status_code=413)(scope, receive, send)


async def _validation_response(_request: Request, exception: RequestValidationError):
    # Pydantic's `input` and exception context can contain credentials or
    # confidential request text. Clients need only the field, type, and reason.
    detail = [
        {"type": error["type"], "loc": error["loc"], "msg": error["msg"]}
        for error in exception.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


def configure_validation_errors(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_response)


def page_params(
    limit: int = Query(PAGE_DEFAULT_LIMIT, ge=1, le=PAGE_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> tuple[int, int]:
    """Standard `?limit=&offset=` paging for list endpoints."""
    return limit, offset
