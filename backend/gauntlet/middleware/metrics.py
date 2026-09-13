"""Operational counters for GAUNTLET itself (SRS 30), exposed at /metrics in Prometheus text format.

These describe the service — request rates, call outcomes, queue depth — and are kept strictly apart from
the product metrics a run measures about a target, so a reader can never mistake one for the other.
Pure ASGI, dependency-free, so streaming responses are never buffered.
"""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.types import ASGIApp, Message, Receive, Scope, Send

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
requests_total: dict[tuple[str, str, int], int] = defaultdict(int)
duration_buckets: dict[str, list[int]] = defaultdict(lambda: [0] * (len(BUCKETS) + 1))
duration_sum: dict[str, float] = defaultdict(float)


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path or "unmatched"


class MetricsMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = {"code": 500}

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            route = _route_template(scope)
            if route != "/metrics":
                elapsed = time.perf_counter() - start
                requests_total[(scope.get("method", "GET"), route, status["code"])] += 1
                idx = next((i for i, b in enumerate(BUCKETS) if elapsed <= b), len(BUCKETS))
                duration_buckets[route][idx] += 1
                duration_sum[route] += elapsed


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"')


def render_http() -> list[str]:
    out = ["# HELP gauntlet_api_requests_total API requests by method, route template and status.",
           "# TYPE gauntlet_api_requests_total counter"]
    for (method, route, code), n in sorted(requests_total.items()):
        out.append(f'gauntlet_api_requests_total{{method="{method}",route="{_esc(route)}",status="{code}"}} {n}')
    out += ["# HELP gauntlet_api_request_duration_seconds API request duration.",
            "# TYPE gauntlet_api_request_duration_seconds histogram"]
    for route, counts in sorted(duration_buckets.items()):
        acc = 0
        for b, c in zip(BUCKETS, counts, strict=False):
            acc += c
            out.append(f'gauntlet_api_request_duration_seconds_bucket{{route="{_esc(route)}",le="{b}"}} {acc}')
        acc += counts[-1]
        out.append(f'gauntlet_api_request_duration_seconds_bucket{{route="{_esc(route)}",le="+Inf"}} {acc}')
        out.append(f'gauntlet_api_request_duration_seconds_sum{{route="{_esc(route)}"}} {duration_sum[route]:.6f}')
        out.append(f'gauntlet_api_request_duration_seconds_count{{route="{_esc(route)}"}} {acc}')
    return out
