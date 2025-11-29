from fastapi import FastAPI
from app.core.config import settings
from app.api.endpoints import market_data, health

app = FastAPI(title=settings.PROJECT_NAME, openapi_url=f"{settings.API_V1_STR}/openapi.json")

app.include_router(market_data.router, prefix=settings.API_V1_STR, tags=["market-data"])
app.include_router(health.router)

@app.get("/")
def root():
    return {"message": "Welcome to Trading System API"}
