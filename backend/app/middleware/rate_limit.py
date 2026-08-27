import time
import logging
from collections import defaultdict
from typing import Dict, List
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("hospital.ratelimit")

class InMemoryRateLimiter(BaseHTTPMiddleware):
    """
    Token bucket sliding window rate limiter:
    - Default: 300 requests per 60 seconds per client IP
    - Excludes health check and static docs
    """
    def __init__(self, app, max_requests: int = 300, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_history: Dict[str, List[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Whitelist health checks, root metadata, and API docs
        if request.url.path in ("/", "/health", "/api/v1/health", "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()

        # Clean old timestamps
        history = self.request_history[client_ip]
        self.request_history[client_ip] = [ts for ts in history if now - ts < self.window_seconds]

        if len(self.request_history[client_ip]) >= self.max_requests:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded. Too many requests. Please retry in a few seconds.",
                    "client_ip": client_ip,
                    "retry_after_seconds": self.window_seconds
                },
                headers={"Retry-After": str(self.window_seconds)}
            )

        self.request_history[client_ip].append(now)
        response = await call_next(request)
        return response
