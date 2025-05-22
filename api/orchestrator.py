from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from api.id_api import _extract_employer_id
from utils.playwright_util import get_valid_glassdoor_tokens
import api.pages_api as pages_api
import api.reviews_api as reviews_api
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class DummyApp:
    def __init__(self):
        self.state = type("S", (), {})()

class DummyRequest:
    def __init__(self, app: DummyApp):
        self.app = app

@router.post(
    "/scrape",
    summary="All-in-one Glassdoor scrape: id → auth → pages → reviews",
)
async def scrape(
    url: str = Query(..., description="Glassdoor company overview URL"),
    pages: Optional[int] = Query(
        None,
        ge=1,
        description="Optional max number of pages to scrape; if omitted, scrapes all pages",
    ),
):
    logger.info(f"Received scrape request for URL: {url}, max pages: {pages}")
    # 1) Extract employer ID
    try:
        employer_id = _extract_employer_id(url)
        logger.info(f"Extracted employer_id: {employer_id} from URL: {url}")
    except Exception as e:
        logger.exception(f"Invalid URL provided: {url}")
        raise HTTPException(status_code=400, detail=f"Invalid URL: {e}")

    # 2) Authenticate using the consolidated token retrieval function
    try:
        logger.info("Attempting to get valid Glassdoor authentication tokens...")
        # Use the new function from playwright_util.py
        auth_tokens = await get_valid_glassdoor_tokens()
        logger.info("Successfully obtained Glassdoor authentication tokens.")
    except Exception as e:
        logger.exception("Failed to get Glassdoor authentication tokens.")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {e}")

    # 3) Prepare dummy state and call /pages to get total_pages
    # If pages_api.get_total_pages is refactored, this changes.
    dummy_app = DummyApp()
    dummy_app.state.employer_id   = employer_id
    dummy_app.state.gd_csrf_token = auth_tokens["gd_csrf_token"]
    dummy_app.state.cookie        = auth_tokens["cookie"]
    dummy_req = DummyRequest(dummy_app)

    try:
        logger.info(f"Fetching total pages for employer_id: {employer_id}")
        pages_resp = await pages_api.get_total_pages(dummy_req)
        total_pages = pages_resp["total_pages"]
        logger.info(f"Total pages found for employer_id {employer_id}: {total_pages}")
    except HTTPException as he:
        logger.warning(f"HTTPException while fetching pages for employer_id {employer_id}: {he.detail}")
        raise he
    except Exception as e:
        logger.exception(f"Error fetching pages for employer_id {employer_id}")
        raise HTTPException(status_code=500, detail=f"Pages API failed: {e}")

    # 4) Apply optional limit
    to_scrape = total_pages
    if pages is not None:
        to_scrape = min(pages, total_pages)
    logger.info(f"Will scrape {to_scrape} pages for employer_id {employer_id}.")

    # Stash it for the reviews step (if reviews_api.get_reviews still uses request.app.state)
    dummy_app.state.total_pages = to_scrape

    # 5) Call /reviews
    try:
        logger.info(f"Fetching reviews for {to_scrape} pages for employer_id: {employer_id}")
        reviews_resp = await reviews_api.get_reviews(dummy_req)
        logger.info(f"Successfully fetched reviews for employer_id {employer_id}.")
    except HTTPException as he:
        logger.warning(f"HTTPException while fetching reviews for employer_id {employer_id}: {he.detail}")
        raise he
    except Exception as e:
        logger.exception(f"Error fetching reviews for employer_id {employer_id}")
        raise HTTPException(status_code=500, detail=f"Reviews API failed: {e}")

    # 6) Return combined result
    final_response = {
        "employer_id":          employer_id,
        # "gd_csrf_token":        auth_tokens["gd_csrf_token"], # Avoid returning sensitive tokens
        # "cookie":               auth_tokens["cookie"],        # Avoid returning sensitive tokens
        "requested_pages_limit": pages if pages is not None else "all",
        "actual_pages_found":   total_pages,
        "actual_pages_scraped": to_scrape,
        **reviews_resp,
    }
    logger.info(f"Scrape completed successfully for employer_id: {employer_id}. Response summary generated.")
    return final_response