from pydantic import BaseModel
from typing import List, Optional

class MarketDataRequest(BaseModel):
    symbol: str = "NSE:NIFTY"
    time_frame: str = "5"
    period: int = 100

class Candle(BaseModel):
    TimeStamp: str
    Open: float
    High: float
    Low: float
    Close: float
    Volume: float

class SaveDataResponse(BaseModel):
    status: str
    file_path: str
    message: Optional[str] = None
