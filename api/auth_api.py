from fastapi import APIRouter, HTTPException, Request          # ← added Request
import auth.csrf_api as csrf_api

router = APIRouter()
@router.get("/csrf", summary="Log in & return gd_csrf_token + cookie")
async def get_csrf(request: Request):                          # ← NEW
    try:
        auth = await csrf_api.extract_tokens()
        # ── SAVE for downstream routes ───────────────────────────────
        request.app.state.gd_csrf_token = auth["gd_csrf_token"]
        request.app.state.cookie = auth["cookie"]
        return auth
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
