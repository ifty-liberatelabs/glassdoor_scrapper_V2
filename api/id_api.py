import re
import logging
from fastapi import APIRouter, Query, HTTPException, Request     # ← added Request

logger = logging.getLogger(__name__)
router = APIRouter()
_ID_PATTERN = re.compile(r"E(\d+)")

def _extract_employer_id(url: str) -> int:
    logger.info(f"Parsing employer ID from URL: {url}")
    m = _ID_PATTERN.search(url)
    if not m:
        logger.error("No employer ID found in URL")
        raise ValueError("No employerId found in the supplied URL.")
    eid = int(m.group(1))
    logger.info(f"Extracted employer_id: {eid}")
    return eid
    

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
        logger.warning(f"Bad request to /id: {err}")
        raise HTTPException(status_code=400, detail=str(err))
