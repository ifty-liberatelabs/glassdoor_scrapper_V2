import json
import os
import asyncio
import logging
import random 
from fastapi import APIRouter, HTTPException, Request
import httpx
import aiofiles

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/reviews", summary="Extract all reviews for an employer and save to JSON files")
async def get_reviews(request: Request):
    logger.info("Starting /reviews scrape")
    if not hasattr(request.app.state, "employer_id"):
        raise HTTPException(
            status_code=400,
            detail="Employer ID not found. Please call /glassdoor/id endpoint first."
        )

    if not hasattr(request.app.state, "gd_csrf_token") or not hasattr(request.app.state, "cookie"):
        raise HTTPException(
            status_code=400,
            detail="Authentication tokens not found. Please call /glassdoor/csrf endpoint first."
        )

    if not hasattr(request.app.state, "total_pages"):
        raise HTTPException(
            status_code=400,
            detail="Total pages not found. Please call /glassdoor/pages endpoint first."
        )

    # Get values from app state
    employer_id = request.app.state.employer_id
    gd_csrf_token = request.app.state.gd_csrf_token
    cookie = request.app.state.cookie
    number_of_pages = request.app.state.total_pages

    # Use employer_id as the folder name
    folder_name = str(employer_id)

    # If the folder already exists, create it with a counter suffix
    counter = 1
    original_folder_name = folder_name
    while os.path.exists(folder_name):
        folder_name = f"{original_folder_name}_{counter}"
        counter += 1

    # Create the folder to store the responses (synchronous is fine for one-time setup)
    os.makedirs(folder_name, exist_ok=True) # Added exist_ok=True

    # API endpoint
    url = "https://www.glassdoor.com/graph"

    saved_files = []

    # It's more efficient to create the httpx.AsyncClient once outside the loop
    async with httpx.AsyncClient(timeout=60.0) as client: # Increased timeout
        for page in range(1, number_of_pages + 1):
            payload_json = json.dumps([ # Renamed to payload_json for clarity
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
            ])

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
                'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"', # Example, keep updated or rotate
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"', # Example
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36', # Example, rotate this
                'Cookie': cookie
            }

            try:
                response = await client.post(url, headers=headers, data=payload_json)
                response.raise_for_status()

                response_data = response.json() # Parse JSON once
                file_path = f"{folder_name}/pg{page}.json"
                
                # Use aiofiles for async file writing
                async with aiofiles.open(file_path, "w") as file:
                    await file.write(json.dumps(response_data, indent=4))

                saved_files.append(file_path)
                logger.info(f"Page {page}/{number_of_pages} saved to {file_path}.")

                # --- DELAY LOGIC ---
                # 1. Delay after each successful scrape
                individual_scrape_delay = random.uniform(0.1, 0.3)
                logger.debug(f"Sleeping for {individual_scrape_delay:.2f}s after page {page}.")
                await asyncio.sleep(individual_scrape_delay)

                # 2. Delay every 10 pages
                if page % 10 == 0:
                    delay_10_pages = random.uniform(0.5, 1.0)
                    logger.info(f"Completed batch ending on page {page}. Sleeping for {delay_10_pages:.2f} seconds…")
                    await asyncio.sleep(delay_10_pages)

                # 3. Delay every 50 pages (this will also trigger the 10-page delay if page is a multiple of 50)
                if page % 50 == 0:
                    delay_50_pages = random.uniform(5.0, 10.0)
                    logger.info(f"Completed major batch ending on page {page}. Sleeping for {delay_50_pages:.2f} seconds…")
                    await asyncio.sleep(delay_50_pages)
                # --- END DELAY LOGIC ---

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTPStatusError for page {page}: Status {e.response.status_code}. Response: {e.response.text[:500]}")
                # Consider more specific error handling for 429 (Too Many Requests) here
                raise HTTPException(status_code=500, detail=f"API request failed for page {page} with status {e.response.status_code}: {e.response.text[:200]}")
            except httpx.RequestError as e:
                logger.error(f"RequestError for page {page}: {type(e).__name__} - {str(e)}")
                raise HTTPException(status_code=500, detail=f"Network request failed for page {page}: {str(e)}")
            except json.JSONDecodeError as e:
                logger.error(f"JSONDecodeError for page {page}: {str(e)}. Response text (first 500 chars): {response.text[:500] if 'response' in locals() and hasattr(response, 'text') else 'Response object not available or no text attribute'}")
                raise HTTPException(status_code=500, detail=f"Failed to parse API response as JSON for page {page}: {str(e)}")
            except (KeyError, IndexError, TypeError) as e:
                logger.error(f"Data parsing error (Key/Index/Type) for page {page}: {type(e).__name__} - {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to process data from API response for page {page}: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error processing or saving page {page}: {type(e).__name__} - {str(e)}")
                logger.exception(f"Full traceback for error on page {page}:") # Log full traceback for unexpected errors
                raise HTTPException(status_code=500, detail=f"Error saving page {page}: {str(e)}")

    logger.info(f"Completed all {number_of_pages} pages for employer {employer_id}.")
    return {
        "employer_id": employer_id,
        "total_pages_processed": number_of_pages, # Or len(saved_files) if you want to be precise about successful saves
        "folder": folder_name,
        "saved_files_count": len(saved_files),
        "status": f"Successfully processed {len(saved_files)} out of {number_of_pages} review pages."
    }