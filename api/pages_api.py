import json
import requests
import logging
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/pages", summary="Get total number of review pages for an employer")
async def get_total_pages(request: Request):
    logger.info("Received request to /pages")
    if not hasattr(request.app.state, "employer_id"):
        logger.warning("Employer ID missing in state")
        raise HTTPException(
            status_code=400, 
            detail="Employer ID not found. Please call /glassdoor/id endpoint first."
        )
    
    if not hasattr(request.app.state, "gd_csrf_token") or not hasattr(request.app.state, "cookie"):
        logger.warning("Auth tokens missing in state")
        raise HTTPException(
            status_code=400, 
            detail="Authentication tokens not found. Please call /glassdoor/csrf endpoint first."
        )
    
    # Get values from app state
    employer_id = request.app.state.employer_id
    gd_csrf_token = request.app.state.gd_csrf_token
    cookie = request.app.state.cookie
    
    # API endpoint
    url = "https://www.glassdoor.com/graph"

    logger.info(f"Fetching total pages for employer_id={employer_id}")

    # Prepare payload
    payload = json.dumps([
        {
            "operationName": "RecordPageView",
            "variables": {
                "employerId": str(employer_id) ,
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
                    "countryId": None,
                    "stateId": None,
                    "metroId": None,
                    "cityId": None
                },
                "onlyCurrentEmployees": False,
                "overallRating": None,
                "page": 1,
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
    
    # Prepare headers
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
        'Cookie': cookie
    }
    
    try:
        # Make the request
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        # Parse the response
        response_data = response.json()
        
        # Extract number of pages
        number_of_pages = response_data[1]['data']['employerReviews']['numberOfPages']
        
        logger.info(f"Total pages for {employer_id}: {number_of_pages}")
        # Save in app state for downstream routes
        request.app.state.total_pages = number_of_pages
        
        return {
            "employer_id": employer_id,
            "total_pages": number_of_pages
        }
        
    except requests.exceptions.RequestException as e:
        logger.exception("Error fetching total pages")
        raise HTTPException(status_code=500, detail=f"API request failed: {str(e)}")
    except (KeyError, IndexError, TypeError) as e:
        logger.exception("Error fetching total pages")
        raise HTTPException(status_code=500, detail=f"Failed to parse API response: {str(e)}")
