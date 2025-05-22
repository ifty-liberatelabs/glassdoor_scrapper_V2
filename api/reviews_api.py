import json
import os
import asyncio
import logging
import random
from fastapi import APIRouter, HTTPException, Request
import httpx
import aiofiles

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_exception, # <--- IMPORT THIS
    RetryError,
    before_sleep_log
)

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Tenacity Configuration ---
RETRYABLE_HTTPX_EXCEPTIONS = (
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.NetworkError,
)
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)

# This function remains the same, it's the predicate logic
def _predicate_should_retry_http_status_error(exception_value: BaseException) -> bool:
    if isinstance(exception_value, httpx.HTTPStatusError):
        should_retry = exception_value.response.status_code in RETRYABLE_STATUS_CODES
        if should_retry:
            logger.warning(f"HTTPStatusError with retryable status code {exception_value.response.status_code} for URL {exception_value.request.url}. Will retry.")
        return should_retry
    return False

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    retry=(
        retry_if_exception_type(RETRYABLE_HTTPX_EXCEPTIONS) |
        retry_if_exception(_predicate_should_retry_http_status_error) # <--- CORRECTED LINE
    ),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True
)
async def fetch_review_page_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    payload_json_str: str,
    page_num: int,
    total_pages: int
):
    logger.info(f"Fetching page {page_num}/{total_pages}...")
    response = await client.post(url, headers=headers, content=payload_json_str)
    response.raise_for_status()
    logger.debug(f"Successfully fetched page {page_num}/{total_pages}. Status: {response.status_code}")
    try:
        return response.json()
    except json.JSONDecodeError as e_json:
        logger.error(f"JSONDecodeError on page {page_num} after successful HTTP request. Response text (first 500 chars): {response.text[:500]}")
        raise


@router.get("/reviews", summary="Extract all reviews for an employer and save to JSON files")
async def get_reviews(request: Request):
    logger.info("Starting /reviews scrape")
    if not hasattr(request.app.state, "employer_id"):
        raise HTTPException(status_code=400, detail="Employer ID not found. Please call /glassdoor/id endpoint first.")
    if not hasattr(request.app.state, "gd_csrf_token") or not hasattr(request.app.state, "cookie"):
        raise HTTPException(status_code=400, detail="Authentication tokens not found. Please call /glassdoor/csrf endpoint first.")
    if not hasattr(request.app.state, "total_pages"):
        raise HTTPException(status_code=400, detail="Total pages not found. Please call /glassdoor/pages endpoint first.")

    employer_id = request.app.state.employer_id
    gd_csrf_token = request.app.state.gd_csrf_token
    cookie = request.app.state.cookie
    number_of_pages = request.app.state.total_pages

    folder_name = str(employer_id)
    counter = 1
    original_folder_name = folder_name
    while os.path.exists(folder_name):
        folder_name = f"{original_folder_name}_{counter}"
        counter += 1
    os.makedirs(folder_name, exist_ok=True)

    url = "https://www.glassdoor.com/graph"
    saved_files = []
    failed_pages_details = []

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    ]

    async with httpx.AsyncClient(timeout=60.0) as client:
        for page in range(1, number_of_pages + 1):
            payload_list = [
                {
                    "operationName": "RecordPageView",
                    "variables": {
                        "employerId": str(employer_id),
                        "pageIdent": "INFOSITE_REVIEWS"
                    },
                    "query": "mutation RecordPageView($employerId: String!, $pageIdent: String!) {\n  recordPageView(\n    pageIdent: $pageIdent\n    metaData: {key: \"employerId\", value: $employerId}\n  ) {\n    totalCount\n    __typename\n  }\n}\n"
                },
                {
                    "operationName": "GetEmployerReviews",
                    "variables": {
                        "applyDefaultCriteria": True,
                        "employerId": int(employer_id),
                        "employmentStatuses": [],
                        "goc": None,
                        "jobTitle": None,
                        "location": {
                            "countryId": None, "stateId": None,
                            "metroId": None, "cityId": None
                        },
                        "onlyCurrentEmployees": False,
                        "overallRating": None,
                        "page": int(page),
                        "preferredTldId": 0,
                        "reviewCategories": [],
                        "sort": "RELEVANCE",
                        "textSearch": "",
                        "worldwideFilter": False,
                        "language": "eng",
                        "useRowProfileTldForRatings": False,
                        "enableKeywordSearch": False
                    },
                    "query": "query GetEmployerReviews($applyDefaultCriteria: Boolean, $dynamicProfileId: Int, $employerId: Int!, $employmentStatuses: [EmploymentStatusEnum], $enableKeywordSearch: Boolean!, $goc: GOCIdent, $isRowProfileEnabled: Boolean, $jobTitle: JobTitleIdent, $language: String, $languageOverrides: [String], $location: LocationIdent, $onlyCurrentEmployees: Boolean, $overallRating: FiveStarRatingEnum, $page: Int!, $preferredTldId: Int, $reviewCategories: [ReviewCategoriesEnum], $sort: ReviewsSortOrderEnum, $textSearch: String, $useRowProfileTldForRatings: Boolean, $worldwideFilter: Boolean) {\n  employerReviews: employerReviewsRG(\n    employerReviewsInput: {applyDefaultCriteria: $applyDefaultCriteria, dynamicProfileId: $dynamicProfileId, employer: {id: $employerId}, employmentStatuses: $employmentStatuses, onlyCurrentEmployees: $onlyCurrentEmployees, goc: $goc, isRowProfileEnabled: $isRowProfileEnabled, jobTitle: $jobTitle, language: $language, languageOverrides: $languageOverrides, location: $location, overallRating: $overallRating, page: {num: $page, size: 10}, preferredTldId: $preferredTldId, reviewCategories: $reviewCategories, sort: $sort, textSearch: $textSearch, useRowProfileTldForRatings: $useRowProfileTldForRatings, worldwideFilter: $worldwideFilter}\n  ) {\n    allReviewsCount\n    currentPage\n    filteredReviewsCount\n    lastReviewDateTime\n    numberOfPages\n    queryJobTitle {\n      id\n      text\n      mgocId\n      __typename\n    }\n    queryLocation {\n      id\n      longName\n      shortName\n      type\n      __typename\n    }\n    ratedReviewsCount\n    ratings {\n      businessOutlookRating\n      careerOpportunitiesRating\n      ceoRating\n      compensationAndBenefitsRating\n      cultureAndValuesRating\n      diversityAndInclusionRating\n      overallRating\n      ratedCeo {\n        id\n        largePhoto: photoUrl(size: LARGE)\n        name\n        regularPhoto: photoUrl(size: REGULAR)\n        title\n        __typename\n      }\n      recommendToFriendRating\n      reviewCount\n      seniorManagementRating\n      workLifeBalanceRating\n      __typename\n    }\n    reviews {\n      advice\n      adviceOriginal\n      cons\n      consOriginal\n      countHelpful\n      countNotHelpful\n      employer {\n        id\n        largeLogoUrl: squareLogoUrl(size: LARGE)\n        regularLogoUrl: squareLogoUrl(size: REGULAR)\n        shortName\n        __typename\n      }\n      employerResponses {\n        id\n        countHelpful\n        countNotHelpful\n        languageId\n        originalLanguageId\n        response\n        responseDateTime(format: ISO)\n        responseOriginal\n        translationMethod\n        __typename\n      }\n      employmentStatus\n      flaggingDisabled\n      featured\n      isCurrentJob\n      jobTitle {\n        id\n        text\n        __typename\n      }\n      languageId\n      lengthOfEmployment\n      location {\n        id\n        type\n        name\n        __typename\n      }\n      originalLanguageId\n      pros\n      prosOriginal\n      ratingBusinessOutlook\n      ratingCareerOpportunities\n      ratingCeo\n      ratingCompensationAndBenefits\n      ratingCultureAndValues\n      ratingDiversityAndInclusion\n      ratingOverall\n      ratingRecommendToFriend\n      ratingSeniorLeadership\n      ratingWorkLifeBalance\n      reviewDateTime\n      reviewId\n      relatedStructures {\n        companyStructureId\n        companyStructureName\n        __typename\n      }\n      summary\n      summaryOriginal\n      textSearchHighlightPhrases @include(if: $enableKeywordSearch) {\n        field\n        phrases {\n          length\n          position: pos\n          __typename\n        }\n        __typename\n      }\n      translationMethod\n      __typename\n    }\n    ratingCountDistribution {\n      overall {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      cultureAndValues {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      careerOpportunities {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      workLifeBalance {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      seniorManagement {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      compensationAndBenefits {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      diversityAndInclusion {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      recommendToFriend {\n        WONT_RECOMMEND\n        RECOMMEND\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"
                }
            ]
            payload_json_str = json.dumps(payload_list)

            headers = {
                'accept': '*/*',
                'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,bn;q=0.7',
                'apollographql-client-name': 'ei-reviews-next',
                'apollographql-client-version': '1.93.0',
                'content-type': 'application/json',
                'gd-csrf-token': gd_csrf_token,
                'origin': 'https://www.glassdoor.com',
                'priority': 'u=1, i',
                'referer': 'https://www.glassdoor.com/',
                'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
                'sec-ch-ua-arch': '"arm"',
                'sec-ch-ua-bitness': '"64"',
                'sec-ch-ua-full-version': '"135.0.7049.85"',
                'sec-ch-ua-full-version-list': '"Google Chrome";v="135.0.7049.85", "Not-A.Brand";v="8.0.0.0", "Chromium";v="135.0.7049.85"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-model': '""',
                'sec-ch-ua-platform': '"macOS"',
                'sec-ch-ua-platform-version': '"15.4.0"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)  AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
                'user-agent': random.choice(user_agents),
                'Cookie': cookie
            }

            try:
                response_data = await fetch_review_page_with_retry(
                    client, url, headers, payload_json_str, page, number_of_pages
                )

                file_path = f"{folder_name}/pg{page}.json"
                async with aiofiles.open(file_path, "w") as file:
                    await file.write(json.dumps(response_data, indent=4))
                saved_files.append(file_path)
                logger.info(f"Page {page}/{number_of_pages} saved to {file_path}.")

            except RetryError as e:
                last_exception = e.last_attempt.exception()
                error_type = type(last_exception).__name__
                error_msg = str(last_exception)
                error_msg_shortened = (error_msg[:150] + '...') if len(error_msg) > 150 else error_msg
                
                logger.error(f"All retries failed for page {page}. Last exception type: {error_type}, Message: {error_msg_shortened}")
                if isinstance(last_exception, httpx.HTTPStatusError):
                    logger.error(f"Last HTTPStatusError for page {page}: Status {last_exception.response.status_code}. Response: {last_exception.response.text[:500]}")
                failed_pages_details.append({"page": page, "error_type": error_type, "error_message": error_msg_shortened})
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTPStatusError (non-retryable or final) for page {page}: Status {e.response.status_code}. Response: {e.response.text[:500]}")
                failed_pages_details.append({"page": page, "error_type": type(e).__name__, "error_message": f"Status {e.response.status_code}: {e.response.text[:200]}"})
            except json.JSONDecodeError as e_json:
                logger.error(f"JSONDecodeError for page {page} (final processing): {str(e_json)}. Doc: {e_json.doc[:200] if hasattr(e_json, 'doc') else 'N/A'}")
                failed_pages_details.append({"page": page, "error_type": type(e_json).__name__, "error_message": str(e_json)})
            except Exception as e:
                logger.error(f"Unexpected error processing page {page} outside fetch: {type(e).__name__} - {str(e)}")
                logger.exception(f"Full traceback for unexpected error on page {page}:")
                failed_pages_details.append({"page": page, "error_type": type(e).__name__, "error_message": str(e)})

            individual_scrape_delay = random.uniform(0.1, 0.3)
            await asyncio.sleep(individual_scrape_delay)
            if page % 10 == 0:
                delay_10_pages = random.uniform(0.5, 1.0)
                logger.info(f"Batch of 10 ending on page {page}. Sleeping for {delay_10_pages:.2f}s…")
                await asyncio.sleep(delay_10_pages)
            if page % 50 == 0:
                delay_50_pages = random.uniform(5.0, 10.0)
                logger.info(f"Major batch of 50 ending on page {page}. Sleeping for {delay_50_pages:.2f}s…")
                await asyncio.sleep(delay_50_pages)

    logger.info(f"Completed all page processing for employer {employer_id}.")
    status_message = f"Successfully saved {len(saved_files)} out of {number_of_pages} review pages."
    if failed_pages_details:
        status_message += f" Failed to process {len(failed_pages_details)} pages."
        logger.warning(f"Failed page details for employer {employer_id}: {failed_pages_details}")

    return {
        "employer_id": employer_id,
        "total_pages_to_scrape": number_of_pages,
        "folder": folder_name,
        "saved_files_count": len(saved_files),
        "failed_pages_count": len(failed_pages_details),
        "failed_pages_details": failed_pages_details,
        "status": status_message
    }