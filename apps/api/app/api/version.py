from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/version")
def version() -> dict:
    git_sha = os.getenv("GIT_SHA") or os.getenv("COMMIT_SHA") or None
    build_time = os.getenv("BUILD_TIME") or None

    if build_time is None:
        build_time = datetime.now(timezone.utc).isoformat()

    return {
        "service": "securitypassport",
        "git_sha": git_sha,
        "build_time": build_time,
    }