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
    retry_if_exception,
    RetryError,
    before_sleep_log
)

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Tenacity Configuration  ---
RETRYABLE_HTTPX_EXCEPTIONS = (
    httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout, httpx.ConnectError,
    httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError, httpx.NetworkError,
)
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)

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
    retry=(retry_if_exception_type(RETRYABLE_HTTPX_EXCEPTIONS) | retry_if_exception(_predicate_should_retry_http_status_error)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True
)
async def fetch_and_save_page(
    client: httpx.AsyncClient,
    url: str,
    headers_template: dict,
    payload_template_list: list,
    page_num: int,
    total_pages_overall: int,
    folder_name: str,
    gd_csrf_token: str,
    cookie: str
):
    logger.info(f"Worker processing page {page_num}/{total_pages_overall}...")
    current_payload_list = json.loads(json.dumps(payload_template_list))
    current_payload_list[1]["variables"]["page"] = int(page_num)
    payload_json_str = json.dumps(current_payload_list)

    current_headers = headers_template.copy()
    current_headers['gd-csrf-token'] = gd_csrf_token
    current_headers['Cookie'] = cookie


    response = await client.post(url, headers=current_headers, content=payload_json_str)
    response.raise_for_status()
    response_data = response.json()

    file_path = f"{folder_name}/pg{page_num}.json"
    async with aiofiles.open(file_path, "w") as file:
        await file.write(json.dumps(response_data, indent=4))
    logger.info(f"Page {page_num}/{total_pages_overall} saved to {file_path}.")
    return file_path


async def page_scraping_worker(
    worker_id: int,
    page_queue: asyncio.Queue,
    client: httpx.AsyncClient,
    base_url: str,
    headers_template: dict,
    payload_template_list: list,
    total_pages_overall: int,
    folder_name: str,
    gd_csrf_token: str,
    cookie: str,
    results_list: list,
    failed_list: list,
    global_page_counter: list,
    global_delay_event: asyncio.Event
):
    logger.info(f"Worker {worker_id}: Starting...")
    pages_processed_in_this_worker_batch = 0
    WORKER_BATCH_SIZE = 5

    while True:
        page_num = None # Initialize page_num to ensure task_done is called correctly in finally
        try:
            # Check if global delay is active BEFORE getting from queue
            if not global_delay_event.is_set(): # If event is cleared, global delay is active
                logger.info(f"Worker {worker_id}: Global delay active, waiting...")
                await global_delay_event.wait() # This will block until event is set
                logger.info(f"Worker {worker_id}: Global delay ended, resuming.")

            page_num = await page_queue.get() # Get a page number or None (sentinel)

            if page_num is None:
                logger.info(f"Worker {worker_id}: Received stop signal (None). Exiting.")
                break # Exit the while loop, worker will terminate

            # If not None, process the page
            try:
                file_path = await fetch_and_save_page(
                    client, base_url, headers_template, payload_template_list,
                    page_num, total_pages_overall, folder_name,
                    gd_csrf_token, cookie
                )
                results_list.append(file_path)
                global_page_counter[0] += 1
            except Exception as e: # Catch errors from fetch_and_save_page (after retries)
                error_type = type(e).__name__
                error_msg = str(e)
                error_msg_shortened = (error_msg[:150] + '...') if len(error_msg) > 150 else error_msg
                logger.error(f"Worker {worker_id}: Failed to process page {page_num}. Error: {error_type} - {error_msg_shortened}")
                if isinstance(e, RetryError) and e.last_attempt:
                     last_exc = e.last_attempt.exception()
                     logger.error(f"Worker {worker_id}: Last exception for page {page_num} was {type(last_exc).__name__}: {str(last_exc)[:200]}")
                     if isinstance(last_exc, httpx.HTTPStatusError):
                         logger.error(f"Worker {worker_id}: Last HTTPStatusError for page {page_num}: Status {last_exc.response.status_code}. Response: {last_exc.response.text[:200]}")
                failed_list.append({"page": page_num, "worker_id": worker_id, "error_type": error_type, "error_message": error_msg_shortened})

            # Per-page delay
            await asyncio.sleep(random.uniform(0.1, 0.3))
            pages_processed_in_this_worker_batch += 1

            if pages_processed_in_this_worker_batch >= WORKER_BATCH_SIZE:
                batch_delay = random.uniform(0.5, 1)
                logger.info(f"Worker {worker_id}: Completed batch of {pages_processed_in_this_worker_batch} pages. Sleeping for {batch_delay:.2f}s...")
                await asyncio.sleep(batch_delay)
                pages_processed_in_this_worker_batch = 0

        except asyncio.CancelledError:
            logger.info(f"Worker {worker_id}: Task cancelled.")
            break # Exit loop on cancellation
        except Exception as e:
            # This catches errors in the worker's own logic (e.g., getting from queue if it raises)
            logger.exception(f"Worker {worker_id}: Unhandled critical exception in worker loop.")
            break # Exit loop on critical error
        finally:
            if page_num is not None: # Ensure task_done is called for actual page numbers
                page_queue.task_done()
            elif page_num is None and hasattr(page_queue, 'task_done'): # Also call for the sentinel None
                page_queue.task_done()


@router.get("/reviews", summary="Extract all reviews for an employer and save to JSON files (concurrent workers with global delay)")
async def get_reviews(request: Request, num_concurrent_workers: int = 1000):
    logger.info(f"Starting /reviews scrape with {num_concurrent_workers} concurrent workers.")
    # ... (initial checks for employer_id, tokens, total_pages remain the same) ...
    if not hasattr(request.app.state, "employer_id"):
        raise HTTPException(status_code=400, detail="Employer ID not found.")
    if not hasattr(request.app.state, "gd_csrf_token") or not hasattr(request.app.state, "cookie"):
        raise HTTPException(status_code=400, detail="Auth tokens not found.")
    if not hasattr(request.app.state, "total_pages"):
        raise HTTPException(status_code=400, detail="Total pages not found.")

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

    base_url = "https://www.glassdoor.com/graph"
    saved_files_results = []
    failed_pages_details = []

    payload_template_list = [
        {
            "operationName": "RecordPageView",
            "variables": {"employerId": str(employer_id), "pageIdent": "INFOSITE_REVIEWS"},
            "query": "mutation RecordPageView($employerId: String!, $pageIdent: String!) {\n  recordPageView(\n    pageIdent: $pageIdent\n    metaData: {key: \"employerId\", value: $employerId}\n  ) {\n    totalCount\n    __typename\n  }\n}\n"
        },
        {
            "operationName": "GetEmployerReviews",
            "variables": {
                "applyDefaultCriteria": True, "employerId": int(employer_id),
                "employmentStatuses": [], "goc": None, "jobTitle": None,
                "location": {"countryId": None, "stateId": None, "metroId": None, "cityId": None},
                "onlyCurrentEmployees": False, "overallRating": None, "page": 0, # Placeholder
                "preferredTldId": 0, "reviewCategories": [], "sort": "RELEVANCE",
                "textSearch": "", "worldwideFilter": False, "language": "eng",
                "useRowProfileTldForRatings": False, "enableKeywordSearch": False
            },
            "query": "query GetEmployerReviews($applyDefaultCriteria: Boolean, $dynamicProfileId: Int, $employerId: Int!, $employmentStatuses: [EmploymentStatusEnum], $enableKeywordSearch: Boolean!, $goc: GOCIdent, $isRowProfileEnabled: Boolean, $jobTitle: JobTitleIdent, $language: String, $languageOverrides: [String], $location: LocationIdent, $onlyCurrentEmployees: Boolean, $overallRating: FiveStarRatingEnum, $page: Int!, $preferredTldId: Int, $reviewCategories: [ReviewCategoriesEnum], $sort: ReviewsSortOrderEnum, $textSearch: String, $useRowProfileTldForRatings: Boolean, $worldwideFilter: Boolean) {\n  employerReviews: employerReviewsRG(\n    employerReviewsInput: {applyDefaultCriteria: $applyDefaultCriteria, dynamicProfileId: $dynamicProfileId, employer: {id: $employerId}, employmentStatuses: $employmentStatuses, onlyCurrentEmployees: $onlyCurrentEmployees, goc: $goc, isRowProfileEnabled: $isRowProfileEnabled, jobTitle: $jobTitle, language: $language, languageOverrides: $languageOverrides, location: $location, overallRating: $overallRating, page: {num: $page, size: 10}, preferredTldId: $preferredTldId, reviewCategories: $reviewCategories, sort: $sort, textSearch: $textSearch, useRowProfileTldForRatings: $useRowProfileTldForRatings, worldwideFilter: $worldwideFilter}\n  ) {\n    allReviewsCount\n    currentPage\n    filteredReviewsCount\n    lastReviewDateTime\n    numberOfPages\n    queryJobTitle {\n      id\n      text\n      mgocId\n      __typename\n    }\n    queryLocation {\n      id\n      longName\n      shortName\n      type\n      __typename\n    }\n    ratedReviewsCount\n    ratings {\n      businessOutlookRating\n      careerOpportunitiesRating\n      ceoRating\n      compensationAndBenefitsRating\n      cultureAndValuesRating\n      diversityAndInclusionRating\n      overallRating\n      ratedCeo {\n        id\n        largePhoto: photoUrl(size: LARGE)\n        name\n        regularPhoto: photoUrl(size: REGULAR)\n        title\n        __typename\n      }\n      recommendToFriendRating\n      reviewCount\n      seniorManagementRating\n      workLifeBalanceRating\n      __typename\n    }\n    reviews {\n      advice\n      adviceOriginal\n      cons\n      consOriginal\n      countHelpful\n      countNotHelpful\n      employer {\n        id\n        largeLogoUrl: squareLogoUrl(size: LARGE)\n        regularLogoUrl: squareLogoUrl(size: REGULAR)\n        shortName\n        __typename\n      }\n      employerResponses {\n        id\n        countHelpful\n        countNotHelpful\n        languageId\n        originalLanguageId\n        response\n        responseDateTime(format: ISO)\n        responseOriginal\n        translationMethod\n        __typename\n      }\n      employmentStatus\n      flaggingDisabled\n      featured\n      isCurrentJob\n      jobTitle {\n        id\n        text\n        __typename\n      }\n      languageId\n      lengthOfEmployment\n      location {\n        id\n        type\n        name\n        __typename\n      }\n      originalLanguageId\n      pros\n      prosOriginal\n      ratingBusinessOutlook\n      ratingCareerOpportunities\n      ratingCeo\n      ratingCompensationAndBenefits\n      ratingCultureAndValues\n      ratingDiversityAndInclusion\n      ratingOverall\n      ratingRecommendToFriend\n      ratingSeniorLeadership\n      ratingWorkLifeBalance\n      reviewDateTime\n      reviewId\n      relatedStructures {\n        companyStructureId\n        companyStructureName\n        __typename\n      }\n      summary\n      summaryOriginal\n      textSearchHighlightPhrases @include(if: $enableKeywordSearch) {\n        field\n        phrases {\n          length\n          position: pos\n          __typename\n        }\n        __typename\n      }\n      translationMethod\n      __typename\n    }\n    ratingCountDistribution {\n      overall {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      cultureAndValues {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      careerOpportunities {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      workLifeBalance {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      seniorManagement {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      compensationAndBenefits {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      diversityAndInclusion {\n        _5\n        _4\n        _3\n        _2\n        _1\n        __typename\n      }\n      recommendToFriend {\n        WONT_RECOMMEND\n        RECOMMEND\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"
        }
    ]
    headers_template = {
        'accept': '*/*', 'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,bn;q=0.7',
        'apollographql-client-name': 'ei-reviews-next', 'apollographql-client-version': '1.93.0',
        'content-type': 'application/json', 'origin': 'https://www.glassdoor.com',
        'referer': 'https://www.glassdoor.com/',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
        'sec-ch-ua-arch': '"arm"', 'sec-ch-ua-bitness': '"64"',
        'sec-ch-ua-full-version': '"135.0.7049.85"',
        'sec-ch-ua-full-version-list': '"Google Chrome";v="135.0.7049.85", "Not-A.Brand";v="8.0.0.0", "Chromium";v="135.0.7049.85"',
        'sec-ch-ua-mobile': '?0', 'sec-ch-ua-model': '""',
        'sec-ch-ua-platform': '"macOS"', 'sec-ch-ua-platform-version': '"15.4.0"',
        'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin',
    }
    # --- END TEMPLATES ---

    page_queue = asyncio.Queue(maxsize=num_concurrent_workers * 2)
    global_page_counter = [0]
    global_delay_event = asyncio.Event()
    global_delay_event.set() # Start with event set (no delay)

    # Task to manage global delays and fill the queue
    async def queue_filler_and_global_delay_manager():
        logger.info("Queue filler: Starting to queue pages.")
        for i in range(1, number_of_pages + 1):
            await page_queue.put(i)
            
            # Check for global 50-page delay
            # This check is based on the counter updated by workers.
            # It's checked after putting an item, so the delay might kick in
            # slightly after the 50th item is processed by a worker.
            if global_page_counter[0] > 0 and global_page_counter[0] % 50 == 0:
                if global_delay_event.is_set(): # Only trigger delay if not already in one
                    global_delay_event.clear()
                    delay_50_pages = random.uniform(1.0, 5.0)
                    logger.info(f"--- GLOBAL: Processed approx {global_page_counter[0]} pages. Initiating global 50-page delay for {delay_50_pages:.2f}s ---")
                    await asyncio.sleep(delay_50_pages)
                    global_delay_event.set()
                    logger.info(f"--- GLOBAL: Global 50-page delay ended. Resuming worker operations. ---")
        
        for _ in range(num_concurrent_workers):
            await page_queue.put(None) # Add sentinels
        logger.info("Queue filler: All pages and sentinels queued.")

    async with httpx.AsyncClient(timeout=60.0) as client:
        filler_task = asyncio.create_task(queue_filler_and_global_delay_manager())

        worker_tasks = []
        for i in range(num_concurrent_workers):
            task = asyncio.create_task(
                page_scraping_worker(
                    worker_id=i + 1, page_queue=page_queue, client=client,
                    base_url=base_url, headers_template=headers_template,
                    payload_template_list=payload_template_list,
                    total_pages_overall=number_of_pages, folder_name=folder_name,
                    gd_csrf_token=gd_csrf_token, cookie=cookie,
                    results_list=saved_files_results, failed_list=failed_pages_details,
                    global_page_counter=global_page_counter,
                    global_delay_event=global_delay_event
                )
            )
            worker_tasks.append(task)

        # Wait for the filler to queue everything up.
        await filler_task
        logger.info("Queue filler task completed.")

        # Wait for all items in the queue to be processed.
        # This means all page numbers and all None sentinels.
        await page_queue.join()
        logger.info("All items from page queue have been processed (task_done called for each).")

        # Now that page_queue.join() has returned, all workers should have received their
        # sentinel None and should be terminating or have terminated.
        # We gather them to ensure they've all finished and to catch any exceptions.
        logger.info("Waiting for all worker tasks to complete...")
        results = await asyncio.gather(*worker_tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Worker {i+1} raised an unhandled exception: {result}")
        logger.info("All worker tasks have completed.")


    logger.info(f"Completed all page processing for employer {employer_id}.")
    status_message = f"Successfully saved {len(saved_files_results)} out of {number_of_pages} review pages using {num_concurrent_workers} workers."
    if failed_pages_details:
        status_message += f" Failed to process {len(failed_pages_details)} pages."
        logger.warning(f"Failed page details for employer {employer_id}: {failed_pages_details}")

    return {
        "employer_id": employer_id,
        "total_pages_to_scrape": number_of_pages,
        "concurrent_workers_used": num_concurrent_workers,
        "folder": folder_name,
        "saved_files_count": len(saved_files_results),
        "failed_pages_count": len(failed_pages_details),
        "failed_pages_details": failed_pages_details,
        "status": status_message
    }