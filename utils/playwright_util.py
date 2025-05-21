import os
import asyncio
from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

load_dotenv()

# ─── 1.  CONFIG  ─────────────────────────────────────────────────────────
EMAIL = os.getenv("GD_EMAIL")
PASSWORD = os.getenv("GD_PASSWORD")

# ─── 2.  APP  ────────────────────────────────────────────────────────────
app = FastAPI(title="Glassdoor helper")

# ─── 3.  CORE SCRAPER  ───────────────────────────────────────────────────
async def extract_tokens() -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        gd_csrf_token: str | None = None

        # Capture gd‑csrf‑token from *any* request header
        def capture(req):
            nonlocal gd_csrf_token
            if "gd-csrf-token" in req.headers:
                gd_csrf_token = req.headers["gd-csrf-token"]
        page.on("request", capture)

        # ➊ open login page
        await page.goto("https://www.glassdoor.com/profile/login_input.htm",
                        wait_until="domcontentloaded", timeout=120_000)

        # ➋ fill email
        await page.fill('input#inlineUserEmail', EMAIL)
        await page.wait_for_selector('button[data-test="continue-with-email-inline"]', timeout=15_000)
        await page.click('button[data-test="continue-with-email-inline"]')


        # ➌ fill password
        await page.wait_for_selector('input#inlineUserPassword', timeout=15_000)
        await page.fill('input#inlineUserPassword', PASSWORD)
        await page.click('form[name="authEmailForm"] button[type="submit"]')

        # ➍ collect cookies & token
        await page.wait_for_timeout(0.5_000)
        cookies = "; ".join(f"{c['name']}={c['value']}" for c in await context.cookies())

        await browser.close()


        if not gd_csrf_token:
            raise RuntimeError("Could not capture gd‑csrf‑token")
            
        
        

        return {"gd_csrf_token": gd_csrf_token, "cookie": cookies}
        

# ─── 4.  ROUTE  ──────────────────────────────────────────────────────────
@app.get("/glassdoor/login")
async def glassdoor_login():
    try:
        data = await extract_tokens()
        return data            # JSON {"gd_csrf_token": "...", "cookie": "..."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

