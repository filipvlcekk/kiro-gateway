import json
from fastapi import Request, Response
from fastapi.responses import JSONResponse

async def api_setup_guard_middleware(request: Request, call_next):
    """Blocks access to /v1/* endpoints if setup is required."""
    is_setup_required = getattr(request.app.state, "setup_required", False)
    
    if is_setup_required and request.url.path.startswith("/v1/"):
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "message": f"Gateway requires configuration. Please visit http://{request.url.hostname}:{request.url.port}/setup in your browser.",
                    "type": "setup_required_error",
                    "code": "setup_required"
                }
            }
        )
    
    return await call_next(request)
