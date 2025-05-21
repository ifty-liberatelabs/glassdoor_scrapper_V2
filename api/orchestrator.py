from fastapi import APIRouter, HTTPException
from api.id_api import _extract_employer_id
from auth.csrf_api import extract_tokens
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
async def scrape(url: str):
    # 1) Extract employer ID
    try:
        employer_id = _extract_employer_id(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {e}")

    # 2) Log in & grab tokens
    try:
        auth = await extract_tokens()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth failed: {e}")

    # Prepare a dummy app state that mimics what your other endpoints expect
    dummy_app = DummyApp()
    dummy_app.state.employer_id   = employer_id
    dummy_app.state.gd_csrf_token = auth["gd_csrf_token"]
    dummy_app.state.cookie        = auth["cookie"]
    dummy_req = DummyRequest(dummy_app)

    # 3) Get total pages
    try:
        pages_resp = await pages_api.get_total_pages(dummy_req)
        total_pages = pages_resp["total_pages"]
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pages failed: {e}")

    # stash it for the final step
    dummy_app.state.total_pages = total_pages

    # 4) Scrape all reviews
    try:
        reviews_resp = await reviews_api.get_reviews(dummy_req)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reviews failed: {e}")

    # Return a combined result
    return {
        "employer_id":   employer_id,
        "gd_csrf_token": auth["gd_csrf_token"],
        "cookie":        auth["cookie"],
        "total_pages":   total_pages,
        "reviews":       reviews_resp,
    }
