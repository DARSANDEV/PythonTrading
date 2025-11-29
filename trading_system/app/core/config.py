import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Trading System API"
    API_V1_STR: str = "/api/v1"
    
    # Data Storage
    STOCK_DATA_PATH: str = "F:\StockData\Charts"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
