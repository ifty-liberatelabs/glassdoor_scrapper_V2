import re
from fastapi import APIRouter, Query, HTTPException, Request     # ← added Request

router = APIRouter()
_ID_PATTERN = re.compile(r"E(\d+)")

def _extract_employer_id(url: str) -> int:
    m = _ID_PATTERN.search(url)
    if not m:
        raise ValueError("No employerId found in the supplied URL.")
    return int(m.group(1))

@router.get("/id", summary="Extract employerId from URL")
async def employer_id(
    request: Request,                     # ← NEW
    url: str = Query(...)
):
    try:
        eid = _extract_employer_id(url)
        # ── SAVE in app.state so other routes can reuse it ───────────
        request.app.state.employer_id = eid
        return {"employer_id": eid}
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
