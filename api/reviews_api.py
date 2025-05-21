import json
import requests
import os
import asyncio 
import logging
from fastapi import APIRouter, HTTPException, Request

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

    # Create the folder to store the responses
    os.makedirs(folder_name)
    
    # API endpoint
    url = "https://www.glassdoor.com/graph"
    
    saved_files = []
    
    for page in range(1, number_of_pages + 1) :
        payload = json.dumps([
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
                        "countryId": None,
                        "stateId": None,
                        "metroId": None,
                        "cityId": None
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
            
            # Save the response as a JSON file for each page in the new folder
            file_path = f"{folder_name}/pg{page}.json"
            with open(file_path, "w") as file:
                json.dump(response.json(), file, indent=4)
            
            saved_files.append(file_path)
            #logger.info(f"Page {page}/{number_of_pages} saved to {file_path}. Sleeping for 2 seconds…")
            #await asyncio.sleep(2)
            logger.info(f"Page {page}/{number_of_pages} saved to {file_path}.")
            if page % 10 == 0:
                logger.info(f"Completed batch ending on page {page}. Sleeping for 0.5 seconds…")
                await asyncio.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=f"API request failed for page {page}: {str(e)}")
        except (KeyError, IndexError, TypeError) as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse API response for page {page}: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error saving page {page}: {str(e)}")
    
    logger.info("Completed all pages")
    # Return summary of the operation
    return {
        "employer_id": employer_id,
        "total_pages": number_of_pages,
        "folder": folder_name,
        "saved_files": saved_files,
        "status": "All review pages successfully saved as JSON files"
    }
