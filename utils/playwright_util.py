import os
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from playwright.async_api import async_playwright
from dotenv import load_dotenv
import httpx # For API validation

from fastapi import FastAPI, HTTPException


logger = logging.getLogger(__name__)
load_dotenv()

# --- CONFIGURATION ---
EMAIL = os.getenv("GD_EMAIL")
PASSWORD = os.getenv("GD_PASSWORD")
TOKEN_FILE_PATH = "auth_tokens.json" 
TOKEN_EXPIRY_HOURS = 24

if not EMAIL or not PASSWORD:
    logger.critical("GD_EMAIL and/or GD_PASSWORD not set in environment. Application will not be able to log in.")

_token_operation_lock = asyncio.Lock()


async def _perform_playwright_login() -> Dict[str, str]:
    """
    Internal function to perform the actual Playwright login and token extraction.
    """
    logger.info("Performing Playwright login to Glassdoor to extract new tokens...")
    if not EMAIL or not PASSWORD:
        raise ValueError("Glassdoor credentials (GD_EMAIL, GD_PASSWORD) are not configured.")

    async with async_playwright() as p:
        logger.info("Launching Playwright browser...")
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        gd_csrf_token: Optional[str] = None

        def capture_csrf_token(req):
            nonlocal gd_csrf_token
            if gd_csrf_token is None and "gd-csrf-token" in req.headers:
                gd_csrf_token = req.headers["gd-csrf-token"]
                logger.debug(f"Captured gd-csrf-token: {gd_csrf_token}")

        page.on("request", capture_csrf_token)

        try:
            await page.goto("https://www.glassdoor.com/profile/login_input.htm",
                            wait_until="domcontentloaded", timeout=120_000)

            await page.fill('input#inlineUserEmail', EMAIL, timeout=30_000)
            await page.wait_for_selector('button[data-test="continue-with-email-inline"]', state="visible", timeout=30_000)
            await page.click('button[data-test="continue-with-email-inline"]')

            await page.wait_for_selector('input#inlineUserPassword', state="visible", timeout=30_000)
            await page.fill('input#inlineUserPassword', PASSWORD)
            await page.wait_for_selector('form[name="authEmailForm"] button[type="submit"]', state="visible", timeout=15_000)
            await page.click('form[name="authEmailForm"] button[type="submit"]')

            # Replace with more robust wait if possible (e.g., wait_for_url or wait_for_selector of logged-in element)
            logger.info("Waiting for login to complete and cookies to settle...")
            await page.wait_for_timeout(0.5_000) # Increased slightly

            if not gd_csrf_token:
                logger.error("Failed to capture gd-csrf-token after login steps.")
                raise RuntimeError("Could not capture gd-csrf-token. Login might have failed.")

            cookies_list = await context.cookies()
            cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies_list)
            logger.info("Playwright login successful, new tokens extracted.")
            return {"gd_csrf_token": gd_csrf_token, "cookie": cookies_str}
        except Exception as e:
            logger.exception("Error during Playwright login process.")
            # Consider saving screenshot: await page.screenshot(path="playwright_error.png")
            raise
        finally:
            logger.debug("Closing Playwright browser after login attempt.")
            await browser.close()


async def _load_tokens_from_file() -> Optional[Dict]:
    if not os.path.exists(TOKEN_FILE_PATH):
        logger.info(f"Token file '{TOKEN_FILE_PATH}' not found.")
        return None
    try:
        with open(TOKEN_FILE_PATH, 'r') as f:
            data = json.load(f)
        if "gd_csrf_token" in data and "cookie" in data and "timestamp" in data:
            logger.info(f"Tokens loaded from '{TOKEN_FILE_PATH}'.")
            return data
        logger.warning(f"Token file '{TOKEN_FILE_PATH}' has invalid structure.")
        return None
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading token file '{TOKEN_FILE_PATH}': {e}")
        return None


async def _save_tokens_to_file(tokens: Dict[str, str], timestamp: datetime):
    data_to_save = {
        "gd_csrf_token": tokens["gd_csrf_token"],
        "cookie": tokens["cookie"],
        "timestamp": timestamp.isoformat()
    }
    try:
        with open(TOKEN_FILE_PATH, 'w') as f:
            json.dump(data_to_save, f, indent=4)
        logger.info(f"Tokens saved to '{TOKEN_FILE_PATH}'.")
    except IOError as e:
        logger.error(f"Error saving token file '{TOKEN_FILE_PATH}': {e}")


async def _is_token_fresh(loaded_tokens: Dict) -> bool:
    try:
        token_timestamp = datetime.fromisoformat(loaded_tokens["timestamp"])
        expiry_timedelta = timedelta(hours=TOKEN_EXPIRY_HOURS)
        if datetime.now() < token_timestamp + expiry_timedelta:
            logger.debug("Loaded tokens are fresh by timestamp.")
            return True
        logger.info("Loaded tokens have expired by timestamp.")
        return False
    except ValueError:
        logger.warning("Invalid timestamp format in token file.")
        return False


async def _validate_tokens_with_api(gd_csrf_token: str, cookie: str) -> bool:
    """
    Attempts a lightweight API call to Glassdoor to see if tokens are still active.
    IMPORTANT: This requires finding a suitable, reliable Glassdoor endpoint.
    The current implementation is a placeholder and needs a real validation target.
    """
    logger.debug("Attempting to validate tokens with a lightweight API call...")
    validation_url = "https://www.glassdoor.com/graph" # Placeholder
    headers = {
        'accept': '*/*', 'content-type': 'application/json',
        'gd-csrf-token': gd_csrf_token, 'Cookie': cookie,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.82 Safari/537.36'
    }
    # Placeholder payload - find a real, simple, authenticated query
    payload = json.dumps([{
        "operationName": "RecordPageView", "variables": {"employerId": "0", "pageIdent": "TOKEN_VALIDATION"},
        "query": "mutation RecordPageView($employerId: String!, $pageIdent: String!) { recordPageView(pageIdent: $pageIdent, metaData: {key: \"employerId\", value: $employerId}) { totalCount __typename } }"
    }])

    try:
        async with httpx.AsyncClient(timeout=15.0) as client: # Increased timeout slightly
            response = await client.post(validation_url, headers=headers, data=payload)
        
        # This validation logic is highly dependent on the chosen endpoint and its responses
        if response.status_code == 200:
            try:
                response_data = response.json()
                # Example: Check if GraphQL response contains data and not errors
                if isinstance(response_data, list) and response_data and "errors" not in response_data[0]:
                    logger.info("Token validation API call successful.")
                    return True
                else:
                    logger.warning(f"Token validation API call returned 200 but indicates failure or error in data: {response.text[:300]}")
                    return False
            except json.JSONDecodeError:
                logger.warning(f"Token validation API call returned 200 but non-JSON response: {response.text[:300]}")
                return False # Treat non-JSON as failure
        elif response.status_code in [401, 403]: # Unauthorized or Forbidden
            logger.warning(f"Token validation API call failed (status {response.status_code}). Tokens likely invalid.")
            return False
        else: # Other HTTP errors
            logger.warning(f"Token validation API call failed with status {response.status_code}: {response.text[:300]}")
            return False # Or True if you want to be optimistic for non-auth errors
    except httpx.RequestError as e:
        logger.error(f"Network error during token validation: {e}")
        return False # Assume invalid if network error occurs
    except Exception:
        logger.exception("Unexpected error during token API validation.")
        return False


async def get_valid_glassdoor_tokens() -> Dict[str, str]:
    """
    Main function to be called by the orchestrator.
    Tries to load valid tokens from file, otherwise performs Playwright login.
    """
    async with _token_operation_lock: # Ensure only one operation at a time
        logger.info("Attempting to retrieve valid Glassdoor tokens...")
        loaded_tokens = await _load_tokens_from_file()

        if loaded_tokens:
            if "gd_csrf_token" not in loaded_tokens or "cookie" not in loaded_tokens or "timestamp" not in loaded_tokens:
                logger.warning("Loaded token structure is invalid. Fetching new tokens.")
            elif await _is_token_fresh(loaded_tokens):
                logger.info("Cached tokens are fresh by timestamp. Validating with API...")
                if await _validate_tokens_with_api(loaded_tokens["gd_csrf_token"], loaded_tokens["cookie"]):
                    logger.info("Cached tokens successfully validated with API. Reusing them.")
                    return {"gd_csrf_token": loaded_tokens["gd_csrf_token"], "cookie": loaded_tokens["cookie"]}
                else:
                    logger.warning("Cached tokens failed API validation despite being fresh. Fetching new tokens.")
            else:
                logger.info("Cached tokens are stale by timestamp. Fetching new tokens.")
        else:
            logger.info("No cached tokens found or file is invalid. Fetching new tokens.")

        # If we reach here, we need new tokens
        try:
            new_tokens = await _perform_playwright_login()
            await _save_tokens_to_file(new_tokens, datetime.now())
            return new_tokens
        except Exception as e:
            logger.exception("Fatal error during token acquisition process.")
            # Re-raise as a more generic error or handle as appropriate for your application
            raise RuntimeError(f"Failed to obtain valid Glassdoor tokens: {e}")


standalone_test_app = FastAPI(title="Glassdoor Token Utility (Standalone Test)")

@standalone_test_app.get("/get-tokens-test", summary="Test the integrated token retrieval logic")
async def test_get_tokens_endpoint():
    logger.info("Received request for /get-tokens-test")
    try:
        tokens = await get_valid_glassdoor_tokens()
        # Be careful about logging sensitive tokens in production
        # logger.info(f"Standalone test successful. Tokens obtained: {tokens}")
        logger.info(f"Standalone test successful. CSRF token obtained, cookie length: {len(tokens.get('cookie', ''))}")
        return {"message": "Tokens obtained successfully (see server logs for details if enabled)", "gd_csrf_token_present": "gd_csrf_token" in tokens}
    except Exception as e:
        logger.exception("Standalone test for /get-tokens-test failed.")
        raise HTTPException(status_code=500, detail=str(e))
