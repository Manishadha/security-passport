from __future__ import annotations

import sentry_sdk
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SentryContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        with sentry_sdk.push_scope() as scope:
            rid = request.headers.get("x-request-id")
            if rid:
                scope.set_tag("request_id", rid)

            scope.set_tag("http.method", request.method)
            scope.set_tag("http.path", request.url.path)

            try:
                response = await call_next(request)
            except Exception as e:
                tid = getattr(request.state, "tenant_id", None)
                uid = getattr(request.state, "user_id", None)
                if tid:
                    scope.set_tag("tenant_id", tid)
                if uid:
                    scope.set_tag("user_id", uid)
                    scope.set_user({"id": uid})

                sentry_sdk.capture_exception(e)
                raise

            tid = getattr(request.state, "tenant_id", None)
            uid = getattr(request.state, "user_id", None)
            if tid:
                scope.set_tag("tenant_id", tid)
            if uid:
                scope.set_tag("user_id", uid)
                scope.set_user({"id": uid})

            scope.set_tag("http.status_code", response.status_code)
            return response