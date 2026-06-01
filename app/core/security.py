"""Optional API key protection for /api routes."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require ``X-API-Key`` on /api/* when ``API_KEY`` is set in the environment."""

    async def dispatch(self, request: Request, call_next):
        if settings.api_key and request.url.path.startswith("/api/"):
            provided = request.headers.get("X-API-Key")
            if provided != settings.api_key:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )
        return await call_next(request)
