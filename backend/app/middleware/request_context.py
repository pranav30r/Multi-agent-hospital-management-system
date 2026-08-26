import time
import uuid
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("hospital.middleware")

class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Production-grade middleware for:
    1. Attaching a unique X-Request-ID header to every request/response for distributed tracing.
    2. Measuring execution latency and injecting X-Process-Time-Ms.
    3. Logging slow requests (> 500ms) for performance monitoring.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", f"REQ-{uuid.uuid4().hex[:8].upper()}")
        request.state.request_id = request_id

        start_time = time.perf_counter()
        response = await call_next(request)
        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(process_time_ms)

        if process_time_ms > 500:
            logger.warning(
                f"[SLOW REQUEST] {request.method} {request.url.path} took {process_time_ms}ms (Request-ID: {request_id})"
            )

        return response
