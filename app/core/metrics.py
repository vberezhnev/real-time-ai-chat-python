import time

from fastapi import Request, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
active_ws_connections = Gauge(
    "active_ws_connections", "Number of active WebSocket connections"
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        path = request.url.path

        if path == "/metrics":
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start

        http_requests_total.labels(method=method, path=path, status=response.status_code).inc()
        http_request_duration_seconds.labels(method=method, path=path).observe(duration)

        return response
