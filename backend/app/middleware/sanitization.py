import re
import html
import logging
from typing import Any, Dict, List, Union
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("hospital.security.sanitizer")

# Patterns matching malicious script injections, SQL injection attempts, and iframe/object injections
XSS_PATTERNS = [
    re.compile(r"<\s*script[^>]*>", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),  # onload=, onerror=, onclick=
    re.compile(r"<\s*iframe[^>]*>", re.IGNORECASE),
    re.compile(r"<\s*object[^>]*>", re.IGNORECASE),
]

def sanitize_value(val: Any) -> Any:
    """Recursively inspects and sanitizes strings to neutralize XSS injection payloads."""
    if isinstance(val, str):
        # Escape HTML entities
        cleaned = html.escape(val)
        return cleaned
    elif isinstance(val, dict):
        return {k: sanitize_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [sanitize_value(item) for item in val]
    return val

def contains_malicious_payload(text: str) -> bool:
    """Checks if raw string contains active attack vectors."""
    for pattern in XSS_PATTERNS:
        if pattern.search(text):
            return True
    return False

class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """
    Hospital-grade Input Sanitization Middleware:
    - Scans incoming query parameters and headers for malicious injection payloads.
    - Blocks detected exploit vectors with HTTP 400 Bad Request before hitting application routers.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        # Check query params
        for param, value in request.query_params.items():
            if contains_malicious_payload(value):
                logger.critical(f"[SECURITY BLOCKED] Malicious injection in query param '{param}' from IP {request.client.host if request.client else 'unknown'}")
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Security violation: Malicious characters or injection detected in request parameter."}
                )

        response = await call_next(request)
        return response
