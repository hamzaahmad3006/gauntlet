"""Structured JSON logging with a field allowlist (SRS-NFR-033/035/036, SRS-SEC-001).

Only allowlisted fields reach the log; any field whose name suggests a secret is dropped even if
allowlisted by mistake. No secrets, no audio, no transcripts — identifiers only.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from gauntlet.middleware.request_id import current_correlation_id

ALLOWED = {"workspace_id", "run_id", "call_id", "actor", "worker_id", "status", "grade", "code", "error",
           "route", "method", "status_code", "duration_ms", "provider", "reason_code"}
SECRETISH = ("key", "secret", "token", "password", "authorization")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": datetime.now(UTC).isoformat(timespec="milliseconds"), "level": record.levelname,
               "logger": record.name, "msg": record.getMessage(), "correlation_id": current_correlation_id()}
        for k, v in record.__dict__.items():
            if k in ALLOWED and not any(s in k.lower() for s in SECRETISH):
                out[k] = v
        if record.exc_info and record.levelno >= logging.ERROR:
            out["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(out, default=str)


def configure(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("websockets", "httpx", "httpcore", "aiosqlite", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
