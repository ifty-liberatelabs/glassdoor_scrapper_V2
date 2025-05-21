import re
import logging
from fastapi import APIRouter, Query, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter()

# Match: -EI_IE<digits>.  OR  -E<digits>.htm
_ID_PATTERN = re.compile(r"-EI_IE(\d+)\.|-E(\d+)\.htm")

def _extract_employer_id(url: str) -> int:
    logger.info(f"Parsing employer ID from URL: {url}")
    match = _ID_PATTERN.search(url)
    if not match:
        logger.error("No employer ID found in URL")
        raise ValueError("No employerId found in the supplied URL.")
    
    # Use the matched group that isn't None
    employer_id_str = match.group(1) or match.group(2)
    if employer_id_str is None:
        raise ValueError("Matched pattern, but could not extract employer ID.")

    eid = int(employer_id_str)
    logger.info(f"Extracted employer_id: {eid}")
    return eid

@router.get("/id", summary="Extract employerId from URL")
async def employer_id(
    request: Request,
    url: str = Query(...)
):
    try:
        eid = _extract_employer_id(url)
        request.app.state.employer_id = eid
        return {"employer_id": eid}
    except ValueError as err:
        logger.warning(f"Bad request to /id: {err}")
        raise HTTPException(status_code=400, detail=str(err))
