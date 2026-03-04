from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from app.core.log_context import ip_var, method_var, path_var, request_id_var, tenant_id_var, user_id_var


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        rid = getattr(record, "request_id", None) or request_id_var.get()
        tid = getattr(record, "tenant_id", None) or tenant_id_var.get()
        uid = getattr(record, "user_id", None) or user_id_var.get()
        ip = getattr(record, "ip", None) or ip_var.get()
        method = getattr(record, "method", None) or method_var.get()
        path = getattr(record, "path", None) or path_var.get()

        if rid is not None:
            base["request_id"] = rid
        if tid is not None:
            base["tenant_id"] = tid
        if uid is not None:
            base["user_id"] = uid
        if ip is not None:
            base["ip"] = ip
        if method is not None:
            base["method"] = method
        if path is not None:
            base["path"] = path

        for k in ("status_code", "duration_ms", "job_run_id", "job_type"):
            if hasattr(record, k):
                base[k] = getattr(record, k)

        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(base, ensure_ascii=False)


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]

    for name in ("uvicorn.access",):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = False

    for name in ("uvicorn.error",):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True