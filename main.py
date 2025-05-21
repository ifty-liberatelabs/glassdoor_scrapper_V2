from fastapi import FastAPI
import api.orchestrator as orchestrator_api
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(message)s"
)


app = FastAPI(
    title="Glassdoor Scraper Suite",
    version="0.3.0"
)

app.include_router(orchestrator_api.router, prefix="/glassdoor", tags=["Orchestrator"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=None,
        log_level="info"
    )