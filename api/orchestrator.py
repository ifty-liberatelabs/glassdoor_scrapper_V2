# api/orchestrator.py

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from api.id_api import _extract_employer_id
from utils.playwright_util import extract_tokens
import api.pages_api as pages_api
import api.reviews_api as reviews_api

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
    # 1) Extract employer ID
    try:
        employer_id = _extract_employer_id(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {e}")

    # 2) Authenticate
    try:
        auth = await extract_tokens()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth failed: {e}")

    # 3) Prepare dummy state and call /pages to get total_pages
    dummy_app = DummyApp()
    dummy_app.state.employer_id   = employer_id
    dummy_app.state.gd_csrf_token = auth["gd_csrf_token"]
    dummy_app.state.cookie        = auth["cookie"]
    dummy_req = DummyRequest(dummy_app)

    try:
        pages_resp = await pages_api.get_total_pages(dummy_req)
        total_pages = pages_resp["total_pages"]
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pages failed: {e}")

    # 4) Apply optional limit
    if pages is not None:
        to_scrape = min(pages, total_pages)
    else:
        to_scrape = total_pages

    # stash it for the reviews step
    dummy_app.state.total_pages = to_scrape

    # 5) Call /reviews
    try:
        reviews_resp = await reviews_api.get_reviews(dummy_req)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reviews failed: {e}")

    # 6) Return combined result
    return {
        "employer_id":          employer_id,
        "gd_csrf_token":        auth["gd_csrf_token"],
        "cookie":               auth["cookie"],
        "requested_pages":      pages if pages is not None else total_pages,
        "actual_pages_scraped": to_scrape,
        **reviews_resp,
    }
