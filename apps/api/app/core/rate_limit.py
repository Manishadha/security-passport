from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Iterable

from redis import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.settings import settings


def _redis() -> Redis:
    return Redis.from_url(settings.redis_url)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    methods: set[str]
    path_prefixes: tuple[str, ...]
    limit: int
    window_seconds: int
    scope: str  # "ip" | "ip_email"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rules: Iterable[RateLimitRule]):
        super().__init__(app)
        self.rules = list(rules)
        self.r = _redis()

    def _match_rule(self, request: Request) -> RateLimitRule | None:
        m = request.method.upper()
        p = request.url.path
        for rule in self.rules:
            if m not in rule.methods:
                continue
            if any(p.startswith(pref) for pref in rule.path_prefixes):
                return rule
        return None

    async def _scope_id(self, request: Request, rule: RateLimitRule) -> str:
        ip = _client_ip(request)

        if rule.scope == "ip":
            return f"ip:{ip}"

        if rule.scope == "ip_email":
            try:
                body = await request.body()
                # Request.body() is cached by Starlette; downstream can still read it.
                import json

                j = json.loads(body.decode("utf-8") or "{}")
                email = (j.get("email") or "").strip().lower()
            except Exception:
                email = ""
            if not email:
                return f"ip:{ip}:email:unknown"
            return f"ip:{ip}:email:{_hash(email)}"

        return f"ip:{ip}"

    async def dispatch(self, request: Request, call_next) -> Response:
        rule = self._match_rule(request)
        if rule is None:
            return await call_next(request)

        scope_id = await self._scope_id(request, rule)

        now = int(time.time())
        window = rule.window_seconds
        window_start = (now // window) * window
        key = f"rl:{rule.name}:{window_start}:{scope_id}"

        try:
            n = self.r.incr(key)
            if n == 1:
                self.r.expire(key, window + 2)

            if n > rule.limit:
                retry_after = (window_start + window) - now
                resp = JSONResponse(
                    status_code=429,
                    content={
                        "detail": "rate limited",
                        "rule": rule.name,
                        "limit": rule.limit,
                        "window_seconds": rule.window_seconds,
                        "retry_after_seconds": max(1, retry_after),
                    },
                )
                resp.headers["Retry-After"] = str(max(1, retry_after))
                return resp
        except Exception:
            # If Redis is down, fail open (do not break the API).
            return await call_next(request)

        return await call_next(request)


def default_rate_limit_rules() -> list[RateLimitRule]:
    return [
        RateLimitRule(
            name="auth_login",
            methods={"POST"},
            path_prefixes=("/auth/login",),
            limit=12,
            window_seconds=60,
            scope="ip_email",
        ),
        RateLimitRule(
            name="exports",
            methods={"POST"},
            path_prefixes=("/exports",),
            limit=30,
            window_seconds=300,
            scope="ip",
        ),
        RateLimitRule(
            name="passport",
            methods={"GET"},
            path_prefixes=("/passport/",),
            limit=60,
            window_seconds=300,
            scope="ip",
        ),
        RateLimitRule(
            name="share_public",
            methods={"GET"},
            path_prefixes=("/share/",),
            limit=120,
            window_seconds=300,
            scope="ip",
        ),
    ]