from fastapi import APIRouter, HTTPException, Request          # ← added Request
import auth.csrf_api as csrf_api
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
@router.get("/csrf", summary="Log in & return gd_csrf_token + cookie")
async def get_csrf(request: Request):
    logger.info("Starting CSRF token + cookie extraction")
    try:
        auth = await csrf_api.extract_tokens()
        logger.info("CSRF token & cookies successfully extracted")
        request.app.state.gd_csrf_token = auth["gd_csrf_token"]
        request.app.state.cookie        = auth["cookie"]
        return auth
    except Exception as exc:
        logger.exception("Failed to extract CSRF token + cookie")
        raise HTTPException(status_code=500, detail=str(exc))
