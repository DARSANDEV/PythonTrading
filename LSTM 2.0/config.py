import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    
    # Data Storage
    STOCK_DATA_SAVING_PATH: str = "./data"
    #get the session id from the tradingview chart
    SESSION_ID: str # SESSION_ID: str = "0.18679.5847_mum1-charts-free-3-tvbs-nril9-3"
    DEBUG: bool = False 
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
