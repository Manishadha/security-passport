from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Callable

import sentry_sdk
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.log_context import (
    ip_var,
    method_var,
    path_var,
    request_id_var,
    tenant_id_var,
    user_id_var,
)

log = logging.getLogger("app.http")


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        ip = _client_ip(request)

        t_rid = request_id_var.set(rid)
        t_ip = ip_var.set(ip)
        t_method = method_var.set(request.method)
        t_path = path_var.set(request.url.path)

        start = time.perf_counter()

        if os.getenv("SENTRY_DSN"):
            sentry_sdk.set_tag("request_id", rid)
            if ip:
                sentry_sdk.set_tag("ip", ip)

        try:
            response = await call_next(request)
        except Exception:
            dur_ms = int((time.perf_counter() - start) * 1000)
            tid = getattr(request.state, "tenant_id", None) or tenant_id_var.get()
            uid = getattr(request.state, "user_id", None) or user_id_var.get()

            log.exception(
                "request_failed",
                extra={
                    "request_id": rid,
                    "tenant_id": tid,
                    "user_id": uid,
                    "ip": ip,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": dur_ms,
                },
            )
            raise
        finally:
            request_id_var.reset(t_rid)
            ip_var.reset(t_ip)
            method_var.reset(t_method)
            path_var.reset(t_path)

        dur_ms = int((time.perf_counter() - start) * 1000)
        tid = getattr(request.state, "tenant_id", None)
        uid = getattr(request.state, "user_id", None)

        if tid is not None:
            tenant_id_var.set(tid)
        if uid is not None:
            user_id_var.set(uid)

        response.headers["X-Request-Id"] = rid

        if not request.url.path.startswith("/health/"):
            log.info(
                "request",
                extra={
                    "request_id": rid,
                    "tenant_id": tid,
                    "user_id": uid,
                    "ip": ip,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": dur_ms,
                },
            )

        return response