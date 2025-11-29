from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.api.models import MarketDataRequest, Candle, SaveDataResponse
from app.services.collector import fetch_historic_data, fetch_live_data_snapshot
from app.services.repository import DataRepository
import pandas as pd

router = APIRouter()

def get_repository():
    return DataRepository()

@router.post("/historic-data", response_model=List[Candle])
def get_historic_data(request: MarketDataRequest):
    """
    Fetch historic market data from TradingView.
    """
    try:
        df = fetch_historic_data(request.symbol, request.time_frame, request.period)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found")
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/live-data", response_model=List[Candle])
def get_live_data(request: MarketDataRequest):
    """
    Fetch live market data snapshot from TradingView.
    """
    try:
        df = fetch_live_data_snapshot(request.symbol, request.time_frame, request.period)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data found")
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/save-historic-data", response_model=SaveDataResponse)
def save_historical_data_to_csv(request: MarketDataRequest, repo: DataRepository = Depends(get_repository)):
    """
    Save historic data to CSV in the configured storage path.
    """
    try:
        path = repo.save_historical_data(request.symbol, request.time_frame, request.period)
        return SaveDataResponse(status="success", file_path=path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/storage/{symbol}", response_model=List[Candle])
def get_historic_data_from_storage(symbol: str, repo: DataRepository = Depends(get_repository)):
    """
    Retrieve the latest saved data for a symbol from storage.
    """
    df = repo.get_historic_data_from_storage(symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found in storage")
    return df.to_dict(orient="records")
